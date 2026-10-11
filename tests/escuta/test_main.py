import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import __main__ as prog
from gabi.escuta.remetentes import aprovar
from gabi.fontes.openrouter import ErroOpenRouter

MIGR = Path(__file__).parent.parent.parent / "migrations"
N = "+5511912345678"
AGORA = dt.datetime(2026, 10, 11, 13, 0, tzinfo=dt.timezone.utc)  # 10:00 em Brasília


class FakeDestinos:
    criados = []

    def __init__(self, paperless, *a, **kw):
        self.kw = kw
        FakeDestinos.criados.append(self)
        self.pedidos, self.crises = [], []

    def pedido(self, con, pid, numero, msg, campos):
        self.pedidos.append(campos)
        self.docs = getattr(self, "docs", []) + [msg["id_externo"]]

    def saude(self, con, msg, campos):
        self.docs = getattr(self, "docs", []) + [msg["id_externo"]]

    def documento(self, con, msg):
        self.docs = getattr(self, "docs", []) + [msg["id_externo"]]

    def crise(self, con, numero, nome, agora=None):
        self.crises.append(numero)


class Modelo:
    def __init__(self, custo=0.01, erro=None):
        self.n, self.custo, self.erro = 0, custo, erro

    def completar(self, prompt, *, forte):
        self.n += 1
        if self.erro:
            raise self.erro
        return json.dumps({"tipo": "pedido", "confianca": 0.95, "campos": {"favorecido": "Maria", "valor": 100}}), self.custo


@pytest.fixture
def amb(tmp_path, monkeypatch):
    banco, spool = tmp_path / "g.db", tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setenv("GABI_ESCUTA_SPOOL", str(spool))
    monkeypatch.setenv("GABI_BANCO", str(banco))
    monkeypatch.setattr(prog, "DestinosReais", FakeDestinos)
    FakeDestinos.criados = []
    con = conectar(banco)
    migrar(con, MIGR)
    aprovar(con, N, "familia", "Joana", "teste")
    return banco, spool, con


def _spool(spool, nome="m1", texto="paga a Maria 100"):
    (spool / f"{nome}.json").write_text(json.dumps({"id_externo": nome, "de": "5511912345678@s.whatsapp.net", "recebida_em": "2026-10-11T09:00:00", "texto": texto}))


def _param(con, chave, valor):
    con.execute("insert or replace into parametro(chave, valor) values (?,?)", (chave, json.dumps(valor)))


def test_main_ingere_e_processa_com_cliente_falso(amb, capsys):
    banco, spool, con = amb
    _spool(spool)
    m = Modelo()
    assert prog.main(cliente=m, agora=AGORA) == 0
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "processada"
    assert m.n == 1
    out = capsys.readouterr().out
    assert "novas=1" in out and "Maria" not in out and N not in out


def test_custo_modelo_inserido_por_chamada_completada(amb):
    banco, spool, con = amb
    _spool(spool)
    prog.main(cliente=Modelo(custo=0.02), agora=AGORA, relogio=lambda: AGORA)
    r = con.execute("select em, custo_usd, tarefa from custo_modelo").fetchall()
    assert len(r) == 1 and r[0]["custo_usd"] == 0.02 and r[0]["tarefa"] == "escuta"
    assert r[0]["em"].startswith("2026-10-11T10:00:00") and r[0]["em"].endswith("-03:00")


def test_chamada_que_falha_nao_grava_custo(amb):
    banco, spool, con = amb
    _spool(spool)
    assert prog.main(cliente=Modelo(erro=ErroOpenRouter("não está configurado")), agora=AGORA) == 0
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 0
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "nova"  # erro da ponte nunca aborta a rodada


def test_orcamento_estourado_pelo_custo_modelo_roda_sem_modelo(amb):
    banco, spool, con = amb
    _param(con, "teto_modelo_dia_usd", 0.05)
    con.execute("insert into custo_modelo(em, custo_usd, tarefa) values ('2026-10-11T08:00:00-03:00', 0.05, 'escuta')")
    _spool(spool)
    m = Modelo()
    assert prog.main(cliente=m, agora=AGORA) == 0
    assert m.n == 0
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "nova"


def test_orcamento_usa_teto_padrao_e_soma_do_mes(amb):
    banco, spool, con = amb
    con.execute("insert into custo_modelo(em, custo_usd, tarefa) values ('2026-10-02T08:00:00-03:00', 17.5, 'x')")
    _spool(spool)
    m = Modelo()
    prog.main(cliente=m, agora=AGORA)
    assert m.n == 0


def test_main_sem_modelo_roda_so_crise(amb):
    banco, spool, con = amb
    _param(con, "escuta.modo", "ativo")
    _param(con, "escuta.palavras_risco", ["quero morrer"])
    _spool(spool, "a", "quero morrer")
    _spool(spool, "b", "paga a Maria 100")
    assert prog.main(cliente=None, agora=AGORA) == 0
    dest = FakeDestinos.criados[0]
    assert dest.crises == [N] and dest.pedidos == []
    estados = {r["id_externo"]: r["estado"] for r in con.execute("select id_externo, estado from escuta_msg")}
    assert estados["a"] == "processada" and estados["b"] == "nova"


def test_main_sem_spool_configurado_falha_claro(amb, monkeypatch, capsys):
    monkeypatch.delenv("GABI_ESCUTA_SPOOL")
    assert prog.main(cliente=Modelo(), agora=AGORA) != 0
    assert "GABI_ESCUTA_SPOOL" in capsys.readouterr().err


def test_main_passa_spool_e_teto_ao_destino(amb):
    banco, spool, con = amb
    _param(con, "escuta.anexo_max_mb", 3)
    prog.main(cliente=Modelo(), agora=AGORA)
    assert FakeDestinos.criados[0].kw == {"spool": spool, "anexo_max_bytes": 3 * 1024 * 1024}


def test_anexo_max_default_25mb(amb):
    banco, spool, con = amb
    prog.main(cliente=Modelo(), agora=AGORA)
    assert FakeDestinos.criados[0].kw["anexo_max_bytes"] == 25 * 1024 * 1024


def test_modo_ativo_vem_do_parametro(amb, monkeypatch):
    banco, spool, con = amb
    _param(con, "escuta.modo", "ativo")
    visto = {}
    real = prog.processar
    monkeypatch.setattr(prog, "processar", lambda *a, **k: visto.update(k, pos=a) or real(*a, **k))
    prog.main(cliente=Modelo(), agora=AGORA)
    assert visto["modo"] == "ativo" and visto["spool"] == spool


def test_ponte_sem_modelo_configurado_vira_cliente_none(monkeypatch):
    class P:
        def __init__(self, *a): ...

        def configurada(self):
            return False
    monkeypatch.setattr(prog, "Ponte", P)
    assert prog.cliente_da_ponte("/x.sock") is None


class Interrompe(Modelo):
    def completar(self, prompt, *, forte):
        if self.n >= 1:
            raise self.saida
        return super().completar(prompt, forte=forte)


@pytest.mark.parametrize("saida", [KeyboardInterrupt, SystemExit])
def test_custo_gravado_na_hora_sobrevive_a_interrupcao(amb, saida, monkeypatch):
    Interrompe.saida = saida
    banco, spool, con = amb
    _spool(spool, "a", "paga a Maria 100")
    _spool(spool, "b", "paga a Ana 200")
    with pytest.raises(saida):
        prog.main(cliente=Interrompe(custo=0.03), agora=AGORA)
    assert [r[0] for r in con.execute("select custo_usd from custo_modelo")] == [0.03]


def test_custo_e_gravado_em_outra_conexao_e_ja_commitado_antes_da_proxima_chamada(amb):
    banco, spool, con = amb
    _spool(spool, "a")
    visto = []

    class Espia(Modelo):
        def completar(self, prompt, *, forte):
            visto.append(con.execute("select count(*) from custo_modelo").fetchone()[0])   # leitura de outra conexão
            return super().completar(prompt, forte=forte)

    class Duvida(Espia):
        def completar(self, prompt, *, forte):
            t, c = Espia.completar(self, prompt, forte=forte)
            return t.replace("0.95", "0.1"), c
    prog.main(cliente=Duvida(), agora=AGORA)   # confiança baixa: 2 chamadas (rápido, forte)
    assert visto == [0, 1]


def test_custo_invalido_vira_custo_fixo_de_reserva(amb):
    banco, spool, con = amb
    for i, c in enumerate((float("nan"), float("inf"), -1.0)):
        _spool(spool, f"m{i}")
        prog.main(cliente=Modelo(custo=c), agora=AGORA)
    assert [r[0] for r in con.execute("select custo_usd from custo_modelo order by id")] == [0.05, 0.05, 0.05]


def test_ponte_inexistente_vira_sem_modelo(tmp_path):
    assert prog.cliente_da_ponte(str(tmp_path / "nao-existe.sock")) is None


def test_sem_spool_o_erro_vai_para_stderr(amb, monkeypatch, capsys):
    monkeypatch.delenv("GABI_ESCUTA_SPOOL")
    prog.main(cliente=Modelo(), agora=AGORA)
    c = capsys.readouterr()
    assert "GABI_ESCUTA_SPOOL" in c.err and c.out == ""


@pytest.mark.parametrize("tipo", ["nada", "saude", "pedido"])
def test_ativo_com_anexo_executa_o_destino_uma_vez_e_um_custo(amb, tipo):
    banco, spool, con = amb
    con.execute("update pessoa set dados=json_set(dados,'$.pode_pedir',json('true'))")
    _param(con, "escuta.modo", "ativo")
    (spool / "anexos").mkdir()
    (spool / "anexos" / "f.pdf").write_text("x")
    (spool / "m1.json").write_text(json.dumps({"id_externo": "m1", "de": "5511912345678@s.whatsapp.net", "recebida_em": "2026-10-11T09:00:00",
                                               "texto": "segue o documento", "anexo": "f.pdf"}))
    resp = {"tipo": tipo, "confianca": 0.95, "campos": {"favorecido": "Maria", "valor": 100} if tipo == "pedido" else {}}

    class M(Modelo):
        def completar(self, prompt, *, forte):
            self.n += 1
            return json.dumps(resp), 0.01
    assert prog.main(cliente=M(), agora=AGORA) == 0
    assert FakeDestinos.criados[0].docs == ["m1"]
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 1
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "processada"


def test_insert_de_custo_que_falha_nao_perde_a_classificacao_e_regrava_depois(amb):
    banco, spool, con = amb

    class Proxy:
        def __init__(self, real):
            self.real, self.falhas = real, 1

        def execute(self, sql, *a):
            if sql.startswith("insert into custo_modelo") and self.falhas:
                self.falhas -= 1
                raise sqlite3.OperationalError("database is locked")
            return self.real.execute(sql, *a)

        def close(self):
            self.real.close()
    w = prog.ModeloComCusto(Modelo(custo=0.02), banco)
    w._con = Proxy(w._con)
    t1, c1 = w.completar("p1", forte=False)
    assert t1 and c1 == 0.02 and len(w.pendentes) == 1
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 0
    w.completar("p2", forte=False)
    assert w.pendentes == [] and con.execute("select count(*) from custo_modelo").fetchone()[0] == 2


def test_insert_pendente_e_regravado_no_fechar(amb):
    banco, spool, con = amb
    w = prog.ModeloComCusto(Modelo(custo=0.02), banco)
    real = w._con
    bloqueada = conectar(banco)
    bloqueada.execute("begin immediate")
    real.execute("pragma busy_timeout=1")
    w.completar("p", forte=False)
    assert len(w.pendentes) == 1
    bloqueada.execute("commit")
    w.fechar()
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 1


def test_custo_pendente_e_gravado_no_fechar_quando_a_rodada_e_interrompida(amb):
    banco, spool, con = amb
    w = prog.ModeloComCusto(Modelo(custo=0.02), banco)
    real = w._con
    bloqueada = conectar(banco)
    real.execute("pragma busy_timeout=1")
    bloqueada.execute("begin immediate")
    w.completar("p", forte=False)               # insert falha: fica pendente
    assert len(w.pendentes) == 1
    bloqueada.execute("commit")
    with pytest.raises(KeyboardInterrupt):
        try:
            raise KeyboardInterrupt
        finally:
            w.fechar()
    assert con.execute("select count(*) from custo_modelo").fetchone()[0] == 1


def test_fechar_que_nao_consegue_gravar_imprime_so_a_contagem(amb, capsys):
    banco, spool, con = amb
    w = prog.ModeloComCusto(Modelo(custo=0.02), banco)
    bloqueada = conectar(banco)
    w._con.execute("pragma busy_timeout=1")
    bloqueada.execute("begin immediate")
    w.completar("p", forte=False)
    w.fechar()
    err = capsys.readouterr().err
    assert "1 linha" in err and "0.02" not in err


def test_main_limpa_orfaos_e_imprime_so_contagem(amb, capsys):
    import os, time
    banco, spool, con = amb
    (spool / "anexos").mkdir()
    o = spool / "anexos" / "segredo-nome.pdf"
    o.write_bytes(b"x")
    t = time.time() - 48 * 3600
    os.utime(o, (t, t))
    assert prog.main(cliente=Modelo(), agora=AGORA) == 0
    out = capsys.readouterr().out
    assert not o.exists() and "orfaos=1" in out and "segredo" not in out


def test_main_escreve_palavras_risco_antes_da_ingestao(amb, capsys):
    banco, spool, con = amb
    _param(con, "escuta.palavras_risco", ["matar"])
    assert prog.main(cliente=None, agora=AGORA) == 0
    assert json.loads((spool / "palavras-risco.json").read_text(encoding="utf-8")) == ["matar"]
    assert "palavras_erro=0" in capsys.readouterr().out


def test_spool_sem_permissao_de_escrita_nao_aborta_a_rodada(amb, capsys, monkeypatch):
    banco, spool, con = amb
    _spool(spool)

    def nega(*a, **kw):
        raise PermissionError("sem escrita")
    monkeypatch.setattr(prog, "escrever_palavras_risco", nega)
    assert prog.main(cliente=None, agora=AGORA) == 0
    out = capsys.readouterr().out
    assert "palavras_erro=1" in out and "ingeridas=1" in out


def test_c1_depois_da_rodada_nenhum_texto_de_mensagem_fica_em_arquivo_do_spool(amb):
    banco, spool, con = amb
    _param(con, "escuta.palavras_risco", ["socorro"])
    _spool(spool, "a", "SEGREDO-APROVADO paga a Maria 100")
    _spool(spool, "b", "SEGREDO-CRISE socorro")
    (spool / "c.json").write_text(json.dumps({"id_externo": "c", "de": "5511900000002@s.whatsapp.net", "recebida_em": "2026-10-11T09:00:00",
                                              "texto": "SEGREDO-DESCONHECIDO"}))
    (spool / "d.json").write_text(json.dumps({"id_externo": "d", "de": "1@g.us", "grupo": True, "id_grupo": "1@g.us",
                                              "recebida_em": "2026-10-11T09:00:00", "texto": "SEGREDO-GRUPO"}))
    assert prog.main(cliente=Modelo(), agora=AGORA) == 0
    assert not (spool / "lidos").exists()
    for f in spool.rglob("*"):
        if f.is_file():
            assert b"SEGREDO" not in f.read_bytes(), f.name


def test_i1_main_passa_o_orcamento_de_tempo_do_parametro(amb, monkeypatch):
    banco, spool, con = amb
    vistos = []
    real = prog.processar

    def espia(*a, **kw):
        vistos.append(kw.get("tempo_max_s"))
        return real(*a, **kw)
    monkeypatch.setattr(prog, "processar", espia)
    prog.main(cliente=None, agora=AGORA)
    _param(con, "escuta.tempo_max_s", 100)
    prog.main(cliente=None, agora=AGORA)
    assert vistos == [420, 100]


def test_i1_teste_crise_grava_um_aviso_de_teste_sem_spool(amb, monkeypatch, capsys):
    banco, spool, con = amb
    monkeypatch.delenv("GABI_ESCUTA_SPOOL")
    assert prog.main(argv=["--teste-crise"]) == 0
    r = con.execute("select tipo, payload from aviso").fetchall()
    assert [(x["tipo"], json.loads(x["payload"])["nome"]) for x in r] == [("escuta_atencao", "TESTE")]
    from gabi.rotas.avisos import descrever
    assert "TESTE" in descrever("escuta_atencao", json.loads(r[0]["payload"]))[0]
    assert "teste" in capsys.readouterr().out
