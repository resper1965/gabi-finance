"""Ferramentas MCP do reembolso de saúde: leem só a projeção do gabi.db (sem a chave do cofre, ADR-014), nunca enviam e nunca trazem nome."""
import datetime as dt
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

FERRAMENTAS = {"reembolso_saude_pendentes": "fin", "reembolso_saude_segunda": "fin", "reembolso_saude_dossie": "docs",
               "reembolso_saude_pedi": "propostas", "reembolso_saude_recebi": "propostas"}


@pytest.fixture
def com_dossies(banco):
    c = conectar(banco)
    agora = "2026-10-08T12:00:00+00:00"
    c.executemany("insert into reembolso_saude_dossie(id, mes, estado, docs, pronto, faltam, doc_ids, parado_desde, atualizado_em) values (?,?,?,?,?,?,?,?,?)", [
        (1, "2026-10", "a_pedir", 2, 0, json.dumps(["comprovante", "conselho"]), "[10, 11]", "2026-10-03", agora),
        (2, "2026-09", "a_pedir", 2, 1, "[]", "[20, 21]", "2026-10-01", agora),
        (3, "2026-09", "pedido", 1, 0, "[]", "[30]", "2026-09-20", agora),
        (4, "2026-08", "a_conferir", 1, 0, "[]", "[40]", "2026-08-20", agora)])
    c.close()
    return banco


@pytest.fixture
def tokens3(com_dossies):
    c = conectar(com_dossies)
    t = {k: emitir(c, k, [k]) for k in ("fin", "docs", "propostas", "sensivel")}
    c.close()
    return t


@pytest.fixture
def cli3(com_dossies):
    with TestClient(criar_mcp(com_dossies, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        yield c


def test_escopos_declarados():
    assert {n: ESCOPOS_FERRAMENTAS[n] for n in FERRAMENTAS} == FERRAMENTAS


def test_pendentes_lista_sem_nome_e_com_o_que_falta(cli3, tokens3):
    d = chamar(cli3, tokens3["fin"], "reembolso_saude_pendentes")["dados"]
    por_id = {x["dossie"]: x for x in d["dossies"]}
    assert set(por_id) == {1, 2, 3, 4}
    assert por_id[1]["faltam"] == ["comprovante", "CRM/CRP"] and por_id[1]["pronto"] is False and por_id[1]["parado_dias"] == 5 and por_id[1]["mes"] == "2026-10"
    assert por_id[2]["pronto"] is True and por_id[3]["estado"] == "pedido"
    assert chamar(cli3, tokens3["fin"], "reembolso_saude_pendentes", estado="a_pedir")["dados"]["dossies"][0]["dossie"] == 1
    assert chamar(cli3, tokens3["fin"], "reembolso_saude_pendentes", estado="x")["erro"] == "requisicao_invalida"


def test_segunda_devolve_o_texto_pronto(cli3, tokens3):
    d = chamar(cli3, tokens3["fin"], "reembolso_saude_segunda")["dados"]
    assert d["texto"] == "\n".join(d["linhas"]) and "• Dossiê 2 (09/2026): pronto para pedir" in d["texto"] and "A conferir:" in d["texto"]


def test_dossie_traz_documentos_e_rascunho_do_pedido_sem_enviar(cli3, tokens3):
    d = chamar(cli3, tokens3["docs"], "reembolso_saude_dossie", dossie_id=2)["dados"]
    assert d["documentos"] == [20, 21] and d["pronto"] is True and d["faltam"] == []
    assert "documentos_baixar" in d["rascunho"] and "20, 21" in d["rascunho"] and "você" in d["rascunho"]
    assert "enviado" not in json.dumps(d).lower()
    f = chamar(cli3, tokens3["docs"], "reembolso_saude_dossie", dossie_id=1)["dados"]
    assert f["pronto"] is False and "Falta: comprovante, CRM/CRP" in f["rascunho"]
    assert chamar(cli3, tokens3["docs"], "reembolso_saude_dossie", dossie_id=99)["erro"] == "nao_encontrado"


def test_escopos_sao_respeitados(cli3, tokens3):
    assert chamar(cli3, tokens3["docs"], "reembolso_saude_pendentes")["erro"] == "sem_escopo"
    assert chamar(cli3, tokens3["fin"], "reembolso_saude_dossie", dossie_id=1)["erro"] == "sem_escopo"
    assert chamar(cli3, tokens3["fin"], "reembolso_saude_pedi", dossie_id=1)["erro"] == "sem_escopo"
    assert chamar(cli3, tokens3["sensivel"], "reembolso_saude_segunda")["erro"] == "sem_escopo"


def test_pedi_so_registra_a_intencao_e_e_idempotente(cli3, com_dossies, tokens3):
    r = chamar(cli3, tokens3["propostas"], "reembolso_saude_pedi", dossie_id=2, protocolo="2026/998-A")["dados"]
    assert r["registrado"] is True and r["aplica_na_proxima_rodada"] is True
    r2 = chamar(cli3, tokens3["propostas"], "reembolso_saude_pedi", dossie_id=2)["dados"]
    assert r2["acao_id"] == r["acao_id"]
    c = conectar(com_dossies)
    a = c.execute("select * from reembolso_saude_acao").fetchall()
    assert len(a) == 1 and (a[0]["dossie_id"], a[0]["acao"], a[0]["protocolo"], a[0]["aplicado_em"]) == (2, "pedi", "2026/998-A", None)
    assert c.execute("select estado from reembolso_saude_dossie where id=2").fetchone()[0] == "a_pedir"  # nada muda antes da rodada


def test_pedi_e_recebi_validam_o_dossie_e_o_protocolo(cli3, tokens3):
    assert chamar(cli3, tokens3["propostas"], "reembolso_saude_pedi", dossie_id=99)["erro"] == "nao_encontrado"
    assert chamar(cli3, tokens3["propostas"], "reembolso_saude_pedi", dossie_id=1, protocolo="x; drop table")["erro"] == "requisicao_invalida"
    assert chamar(cli3, tokens3["propostas"], "reembolso_saude_pedi", dossie_id=3)["erro"] == "requisicao_invalida"   # já pedido
    assert chamar(cli3, tokens3["propostas"], "reembolso_saude_recebi", dossie_id=1)["erro"] == "requisicao_invalida"  # nada pedido ainda
    assert chamar(cli3, tokens3["propostas"], "reembolso_saude_recebi", dossie_id=3)["dados"]["registrado"] is True
