import datetime as dt
import json
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

    def saude(self, con, msg, campos): ...

    def documento(self, con, msg): ...

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
    prog.main(cliente=Modelo(custo=0.02), agora=AGORA)
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
    assert "GABI_ESCUTA_SPOOL" in capsys.readouterr().out


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
