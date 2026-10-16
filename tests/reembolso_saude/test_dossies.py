"""Regras de reembolso (puras): o que entra, o que reabre, o que falta. Portadas dos testes do gabi-fin."""
import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.reembolso_saude import dossies
from gabi.reembolso_saude.requisitos import validar

H = dt.date(2026, 10, 10)
SEED = Path(__file__).parent.parent.parent / "seeds" / "reembolso-saude-requisitos.json"
COMPLETO = {"valor": "300.00", "doc_prestador": "x", "conselho": "123", "especialidade": "pediatria"}


@pytest.fixture
def req():
    return validar(json.loads(SEED.read_text(encoding="utf-8")))


def d(i, tipo, caso="consulta", adicionado=H, data=H, estado="a_pedir", **campos):
    base = {"paciente": "Bia", "prestador": "Dra. Ana Lima"}
    base.update(campos)
    return {"id": i, "estado": estado, "documento": tipo, "caso": caso, "campos": base, "data": data, "adicionado": adicionado, "pedido_em": None}


def test_consulta_com_recibo_sem_nf(req):
    assert dossies.estado_pelo_portao("consulta", {"recibo", "comprovante"}, req) == "sem_nf"


def test_consulta_com_nf_a_pedir(req):
    assert dossies.estado_pelo_portao("consulta", {"nf"}, req) == "a_pedir"


def test_tratamento_sem_autorizacao(req):
    assert dossies.estado_pelo_portao("tratamento", {"nf"}, req) == "sem_aprovacao"


def test_autorizacao_reabre_ate_90_dias(req):
    aut = d(9, "autorizacao", caso="tratamento", estado="autorizacao")
    no_prazo = d(1, "nf", caso="tratamento", adicionado=H - dt.timedelta(days=90), estado="sem_aprovacao")
    velho = d(2, "nf", caso="tratamento", adicionado=H - dt.timedelta(days=91), estado="sem_aprovacao")
    assert [x["id"] for x in dossies.reabrir([aut, no_prazo, velho], H, req)] == [1]


def test_sem_autorizacao_nao_reabre(req):
    assert dossies.reabrir([d(1, "nf", caso="tratamento", estado="sem_aprovacao")], H, req) == []


def test_nf_reabre_recibo(req):
    assert [x["id"] for x in dossies.reabrir([d(1, "recibo", estado="sem_nf"), d(2, "nf")], H, req)] == [1]


def test_nf_de_outro_mes_nao_vale_para_consulta(req):
    nf_ago = d(1, "nf", data=dt.date(2026, 8, 5))
    rec_out = d(2, "recibo", estado="sem_nf")
    assert dossies.reabrir([nf_ago, rec_out], H, req) == []
    assert "nf" not in dossies.itens_portao(rec_out, [nf_ago, rec_out])
    assert "nf" in dossies.itens_portao(rec_out, [d(3, "nf"), rec_out])


def test_autorizacao_vale_para_o_par_de_qualquer_mes(req):
    aut = d(9, "autorizacao", caso="tratamento", data=dt.date(2026, 6, 1), estado="autorizacao")
    nf = d(1, "nf", caso="tratamento", estado="sem_aprovacao")
    assert [x["id"] for x in dossies.reabrir([aut, nf], H, req)] == [1]


def test_pedido_e_recebido_nao_reabrem(req):
    assert dossies.reabrir([d(1, "recibo", estado="pedido"), d(2, "nf")], H, req) == []


def test_chave_do_dossie_normaliza():
    a = d(1, "recibo", prestador="Dra. Ana Lima")
    b = d(2, "recibo", prestador="ana  lima", paciente="BIA")
    c = d(3, "recibo", data=H - dt.timedelta(days=40))
    assert dossies.chave(a) == dossies.chave(b) != dossies.chave(c)


def test_norm_tira_acento_e_titulo():
    assert dossies.norm("Dr. João  Ávila") == "joao avila"


def test_itens_do_doc():
    assert dossies.itens_do_doc(d(1, "nf", **COMPLETO)) == {"nf", "data", "paciente", "prestador", "valor", "doc_prestador", "conselho", "especialidade"}


def test_faltando_vem_dos_requisitos(req):
    docs = [d(1, "nf", valor="1")]
    assert "especialidade" in dossies.faltando(docs, req)
    r2 = copy.deepcopy(req)
    r2["todos"].remove("especialidade")
    assert "especialidade" not in dossies.faltando(docs, r2)


def test_faltando_na_ordem_do_arquivo(req):
    assert dossies.faltando([d(1, "nf")], req) == ["comprovante", "valor", "doc_prestador", "conselho", "especialidade"]


def test_faltando_tratamento_pede_relatorio(req):
    docs = [d(1, "nf", caso="tratamento", **COMPLETO), d(2, "comprovante", caso="tratamento"), d(3, "pedido_medico", caso="tratamento")]
    assert dossies.faltando(docs, req) == ["relatorio"]


def test_resumo_pronto_e_parado(req):
    docs = [d(1, "nf", adicionado=H - dt.timedelta(days=5), **COMPLETO), d(2, "comprovante", adicionado=H - dt.timedelta(days=3))]
    (r,) = dossies.resumo(docs, H, req)
    assert r["pronto"] and r["faltam"] == [] and r["docs"] == [1, 2] and r["parado_dias"] == 3 and r["mes"] == "2026-10"
    assert r["paciente"] == "Bia" and r["prestador"] == "Dra. Ana Lima"


def test_resumo_separa_dossies_por_mes_e_paciente(req):
    docs = [d(1, "nf"), d(2, "nf", data=H - dt.timedelta(days=40)), d(3, "nf", paciente="Teo")]
    assert len(dossies.resumo(docs, H, req)) == 3


def test_casar_credito_valor_total_unico():
    doc = {"campos": {"valor": "312.45"}, "pedido_em": dt.date(2026, 10, 1)}
    txs = [{"id": 1, "data": "2026-10-09", "descricao": "CREDITO SULAMERICA SEG", "valor_centavos": 30000},
           {"id": 2, "data": "2026-10-09", "descricao": "PIX JOAO", "valor_centavos": 30000}]
    assert dossies.casar_credito(doc, txs, "SULAMERICA") == 1


def test_casar_credito_ambiguo_ou_antes_do_pedido_ou_acima_do_total_nao_casa():
    doc = {"campos": {"valor": "312.45"}, "pedido_em": dt.date(2026, 10, 1)}
    dois = [{"id": i, "data": "2026-10-09", "descricao": "SULAMERICA", "valor_centavos": 10000} for i in (1, 2)]
    assert dossies.casar_credito(doc, dois, "SULAMERICA") is None
    assert dossies.casar_credito(doc, [{"id": 1, "data": "2026-09-20", "descricao": "SULAMERICA", "valor_centavos": 10000}], "SULAMERICA") is None
    assert dossies.casar_credito(doc, [{"id": 1, "data": "2026-10-09", "descricao": "SULAMERICA", "valor_centavos": 99999}], "SULAMERICA") is None
    assert dossies.casar_credito(doc, [{"id": 1, "data": "2026-10-09", "descricao": "SULAMERICA", "valor_centavos": -10000}], "SULAMERICA") is None


def test_valor_centavos_aceita_formatos():
    assert [dossies.centavos(v) for v in ("312.45", "BRL312.45", "312,45", "1.234,56", 10, None, "x")] == [31245, 31245, 31245, 123456, 1000, None, None]
