"""Rodada de leitura: Paperless e modelo falsos, banco temporário. Consome: gabi.documentos.leitura, __main__."""
import datetime as dt
import json
import logging
from pathlib import Path

import pytest

from gabi.correio.modelo import Falha
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import Orcamento
from gabi.documentos import leitura
from gabi.documentos.leitura import ler

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 23, 8, 0, tzinfo=dt.timezone.utc)
OCR = "Passaporte da Republica Federativa do Brasil. Titular Ana Souza. Numero FK077009 validade 2030"


class Paperless:
    def __init__(self, *docs):
        self.lista, self.pedidos = list(docs), []

    def docs(self, **filtros):
        return [dict(d) for d in self.lista]

    def documento(self, id):
        self.pedidos.append(id)
        return next(d for d in self.lista if d["id"] == id)


def _d(id, content=OCR, modified="2026-10-01T10:00:00Z", title="Doc"):
    return {"id": id, "title": title, "modified": modified, "content": content}


def _resp(**kw):
    d = {"relevante": True, "tipo": "passaporte", "pais": "BR", "emissor": "PF",
         "titular": {"nome": "Ana Souza", "cpf": None, "placa": None, "renavam": None, "matricula": None, "endereco": None},
         "numeros": [{"nome": "numero", "valor": "FK077009"}], "datas": [{"tipo": "validade", "data": "2030-01-01"}]}
    d.update(kw)
    return json.dumps(d)


class Modelo:
    def __init__(self, *respostas):
        self.respostas, self.n = list(respostas), 0

    def completar(self, prompt, *, forte):
        self.n += 1
        return (self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]), 0.001


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana Souza','{}')")
    return c


def _ler(con, pl, cli, max_por=50):
    return ler(con, pl, cli, Orcamento(teto_dia_usd=1.0, teto_mes_usd=10.0), AGORA, max_por_rodada=max_por, max_caracteres=12000)


def _estado(con, pid):
    return con.execute("select * from documento_leitura where paperless_id=?", (pid,)).fetchone()


def test_le_documento_e_propoe(con):
    r = _ler(con, Paperless(_d(1)), Modelo(_resp()))
    assert (r.lidos, r.propostas, r.falhas) == (1, 1, 0)
    p = con.execute("select * from documento_proposta").fetchall()
    assert len(p) == 1 and p[0]["origem"] == "leitura" and p[0]["paperless_id"] == 1 and p[0]["conferir"] == 0
    assert _estado(con, 1)["estado"] == "lido" and con.execute("select count(*) from documento").fetchone()[0] == 0


def test_segunda_rodada_sem_mudanca_nao_chama_nem_propoe(con):
    pl, m = Paperless(_d(1)), Modelo(_resp())
    _ler(con, pl, m)
    r = _ler(con, pl, m)
    assert m.n == 1 and (r.lidos, r.propostas) == (0, 0)
    assert con.execute("select count(*) from documento_proposta").fetchone()[0] == 1


def test_modified_novo_com_data_nova_gera_proposta_que_substitui(con):
    pl, m = Paperless(_d(1)), Modelo(_resp())
    _ler(con, pl, m)
    ant = con.execute("select id from documento_proposta").fetchone()[0]
    from gabi.documentos import repositorio as rep
    rep.decidir(con, ant, "aprovada", "ricardo", AGORA)
    pl.lista = [_d(1, modified="2026-10-05T10:00:00Z", content=OCR.replace("2030", "2035"))]
    m.respostas = [_resp(datas=[{"tipo": "validade", "data": "2035-01-01"}])]
    r = _ler(con, pl, m)
    assert r.propostas == 1 and m.n == 2
    assert con.execute("select documento_id from documento_proposta where estado='pendente'").fetchone()[0] is not None
    assert _estado(con, 1)["modificado"] == "2026-10-05T10:00:00Z"


def test_so_pendentes_e_teto_por_rodada(con):
    pl = Paperless(_d(1), _d(2), _d(3))
    m = Modelo(_resp(numeros=[]))
    r = _ler(con, pl, m, max_por=2)
    assert m.n == 2 and r.lidos == 2 and _estado(con, 3) is None
    _ler(con, pl, m, max_por=2)
    assert _estado(con, 3)["estado"] == "lido" and m.n == 3


def test_ocr_curto_e_sem_texto_sem_modelo(con):
    m = Modelo(_resp())
    r = _ler(con, Paperless(_d(1, content="  ab 12 \n ... --- ")), m)
    assert r.sem_texto == 1 and m.n == 0 and _estado(con, 1)["estado"] == "sem_texto"
    r = _ler(con, Paperless(_d(2, content=None)), m)
    assert r.sem_texto == 1 and m.n == 0


def test_conteudo_ausente_na_listagem_busca_documento(con):
    d = _d(1)
    del d["content"]
    pl = Paperless(d)
    pl.lista[0]["content"] = OCR  # visível só por documento(); docs() devolve cópia sem content
    pl.docs = lambda **f: [{k: v for k, v in x.items() if k != "content"} for x in pl.lista]
    r = _ler(con, pl, Modelo(_resp()))
    assert pl.pedidos == [1] and r.propostas == 1


def test_sem_documento(con):
    m = Modelo(json.dumps({"relevante": False}))
    r = _ler(con, Paperless(_d(1)), m)
    assert r.sem_documento == 1 and _estado(con, 1)["estado"] == "sem_documento"
    _ler(con, Paperless(_d(1)), m)
    assert m.n == 1


def test_documento_invalido_falha_com_tentativa(con, monkeypatch):
    monkeypatch.setattr(leitura.extracao, "conferir", lambda *a: (None, None, ["documento_invalido"]))
    r = _ler(con, Paperless(_d(1)), Modelo(_resp(tipo="x", datas=[], numeros=[])))
    e = _estado(con, 1)
    assert r.falhas == 1 and e["estado"] == "falhou" and e["tentativas"] == 1 and e["motivo"] == "documento_invalido"


def test_numero_nao_confere_vira_proposta_conferir(con):
    _ler(con, Paperless(_d(1)), Modelo(_resp(numeros=[{"nome": "numero", "valor": "ZZ999999"}])))
    p = con.execute("select conferir, motivos from documento_proposta").fetchone()
    assert p["conferir"] == 1 and "numero_nao_confere" in json.loads(p["motivos"])


def test_falha_temporaria_ate_3_tentativas(con, monkeypatch):
    monkeypatch.setattr(leitura.extracao, "extrair", lambda *a, **k: Falha("resposta do modelo sem JSON válido", True))
    pl = Paperless(_d(1))
    for i in (1, 2, 3):
        r = _ler(con, pl, Modelo(_resp()))
        assert r.falhas == 1 and _estado(con, 1)["tentativas"] == i
    r = _ler(con, pl, Modelo(_resp()))
    assert r.falhas == 0 and _estado(con, 1)["tentativas"] == 3 and _estado(con, 1)["estado"] == "falhou"
    pl.lista = [_d(1, modified="2026-11-01T00:00:00Z")]
    assert _ler(con, pl, Modelo(_resp())).falhas == 1 and _estado(con, 1)["tentativas"] == 1
    assert not any(c.isdigit() for c in _estado(con, 1)["motivo"])


def test_falha_definitiva_para_a_rodada_sem_marcar(con, monkeypatch):
    monkeypatch.setattr(leitura.extracao, "extrair", lambda *a, **k: Falha("sem modelo", False))
    r = _ler(con, Paperless(_d(1), _d(2)), Modelo(_resp()))
    assert r.parada == "sem modelo" and _estado(con, 1) is None and _estado(con, 2) is None and r.falhas == 0


def test_paperless_documento_falha_vira_falhou(con):
    d = _d(1)
    del d["content"]

    class Ruim(Paperless):
        def docs(self, **f):
            return [d]

        def documento(self, id):
            raise RuntimeError("fora")
    r = _ler(con, Ruim(d), Modelo(_resp()))
    assert r.falhas == 1 and _estado(con, 1)["motivo"] == "paperless_indisponivel"


def test_log_e_motivo_sem_numero_nem_texto(con, caplog):
    caplog.set_level(logging.DEBUG)
    _ler(con, Paperless(_d(1), _d(2, content="x")), Modelo(_resp(numeros=[{"nome": "numero", "valor": "ZZ999999"}])))
    tudo = caplog.text + json.dumps([dict(r) for r in con.execute("select motivo from documento_leitura")])
    for segredo in ("FK077009", "ZZ999999", "Ana Souza"):
        assert segredo not in tudo


def test_main_imprime_so_contagens(tmp_path, capsys):
    from gabi.documentos.__main__ import main
    banco = tmp_path / "g.db"
    c = conectar(banco)
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana Souza','{}')")
    c.close()
    assert main(banco, paperless=Paperless(_d(1)), cliente=Modelo(_resp()), agora=AGORA) == 0
    out = capsys.readouterr().out
    assert out.strip() == "documentos: lidos=1 propostas=1 sem_texto=0 sem_documento=0 falhas=0"
    assert "FK077009" not in out


# ---------------- fix wave (revisão final) ----------------

def test_sem_modelo_nao_gasta_tentativa_com_extrair_de_verdade(con):
    """I2: cliente None com o `extrair` real (sem monkeypatch): para a rodada e não toca em documento_leitura."""
    r = _ler(con, Paperless(_d(1), _d(2)), None)
    assert r.parada == "modelo não configurado" and r.falhas == 0
    assert con.execute("select count(*) from documento_leitura").fetchone()[0] == 0


def test_main_sem_modelo_sai_0_com_parada(tmp_path, capsys):
    from gabi.documentos.__main__ import main
    banco = tmp_path / "g.db"
    c = conectar(banco)
    migrar(c, MIGRACOES)
    c.close()
    assert main(banco, paperless=Paperless(_d(1)), cliente=None, agora=AGORA) == 0
    assert "parada=modelo não configurado" in capsys.readouterr().out
    c = conectar(banco)
    assert c.execute("select count(*) from documento_leitura").fetchone()[0] == 0
    assert c.execute("select erro from rodada where fonte='documentos'").fetchone()[0] == "parada: modelo não configurado"


class ForaDoAr:
    def __init__(self):
        self.n = 0

    def completar(self, prompt, *, forte):
        self.n += 1
        raise TimeoutError("timeout")


def test_modelo_fora_do_ar_para_a_rodada_sem_gastar_tentativa(con):
    """I2b: 3 falhas temporárias seguidas do modelo param a rodada e não contam tentativa para esses 3."""
    m = ForaDoAr()
    r = _ler(con, Paperless(*(_d(i) for i in range(1, 6))), m)
    assert r.parada == "modelo indisponível" and r.falhas == 0 and m.n == 6  # fraco e forte em cada um dos 3
    assert con.execute("select count(*) from documento_leitura").fetchone()[0] == 0
    for _ in range(4):  # rodadas seguidas fora do ar nunca esgotam as tentativas
        assert _ler(con, Paperless(*(_d(i) for i in range(1, 6))), ForaDoAr()).parada == "modelo indisponível"
    assert con.execute("select count(*) from documento_leitura").fetchone()[0] == 0


def test_falha_temporaria_isolada_conta_tentativa(con, monkeypatch):
    """I2b: uma ou duas falhas temporárias seguidas de um documento que dá certo contam tentativa normalmente."""
    respostas = iter([Falha("falha temporária do modelo", True), json.loads(_resp())])
    monkeypatch.setattr(leitura.extracao, "extrair", lambda *a, **k: next(respostas))
    r = _ler(con, Paperless(_d(1), _d(2)), Modelo(_resp()))
    assert r.parada is None and r.falhas == 1 and _estado(con, 1)["tentativas"] == 1 and _estado(con, 2)["estado"] == "lido"


def test_prompt_leva_a_data_do_documento(con):
    """U6: a data do Paperless (`created`) vai no prompt, dentro do bloco de dados."""
    class Guarda(Modelo):
        def completar(self, prompt, *, forte):
            self.prompt = prompt
            return super().completar(prompt, forte=forte)
    m = Guarda(_resp())
    d = _d(1)
    d["created"] = "2024-03-05T00:00:00-03:00"
    _ler(con, Paperless(d), m)
    assert "Data: 2024-03-05" in m.prompt
    assert m.prompt.index("=====INICIO_") < m.prompt.index("Data: 2024-03-05") < m.prompt.index("=====FIM_")
