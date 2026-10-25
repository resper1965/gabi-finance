"""Ferramentas de leitura da Onda 2 (`contatos_buscar`). Consome: gabi.mcp.ferramentas_ver, fixtures de tests/mcp/test_servidor.py."""
import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.ferramentas_ver import buscar_contatos
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, criar_mcp, ferramentas_do_token
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

TEL = "+5511993290462"


@pytest.fixture
def con(banco):
    c = conectar(banco)
    yield c
    c.close()


def _google(con, conta, tel, nome):
    con.execute("insert into contato_google(conta, telefone, nome) values (?,?,?)", (conta, tel, nome))


def test_buscar_sem_acento(con):
    _google(con, "a@x", TEL, "João Silva")
    assert buscar_contatos(con, "joao")["itens"][0]["nome"] == "João Silva"


def test_buscar_por_pedaco_do_telefone(con):
    _google(con, "a@x", TEL, "João Silva")
    itens = buscar_contatos(con, "99329")["itens"]
    assert len(itens) == 1 and itens[0]["telefones"] == [TEL]


def test_junta_google_e_graph(con):
    _google(con, "a@x", TEL, "Ana")
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness','g1','Ana N','(11) 99329-0462',?,'mobile','2026-10-01')", (TEL,))
    itens = buscar_contatos(con, "ana")["itens"]
    assert len(itens) == 1 and itens[0]["nome"] == "Ana" and itens[0]["origens"] == ["google:a@x", "graph:r@ness"]


def test_nome_do_graph_quando_google_sem_nome(con):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness','g1','Beto','x',?,'mobile','2026-10-01')", (TEL,))
    assert buscar_contatos(con, "beto")["itens"][0]["nome"] == "Beto"


def test_email_entra_no_item(con):
    _google(con, "a@x", TEL, "Ana")
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values ('a@x','ana@y.com',?,'Ana')", (TEL,))
    itens = buscar_contatos(con, "ana@y")["itens"]
    assert len(itens) == 1 and itens[0]["emails"] == ["ana@y.com"] and itens[0]["telefones"] == [TEL]


def test_email_sem_telefone_vira_item_proprio(con):
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values ('a@x','zé@y.com','','Zé')")
    it = buscar_contatos(con, "zé@y")["itens"][0]
    assert it["telefones"] == [] and it["emails"] == ["zé@y.com"] and it["origens"] == ["google:a@x"]


def test_texto_curto(con):
    with pytest.raises(ValueError):
        buscar_contatos(con, " a ")


def test_limite(con):
    for i, t in enumerate(("+5511993290461", "+5511993290462", "+5511993290463")):
        _google(con, "a@x", t, f"Maria {i}")
    assert len(buscar_contatos(con, "maria", limite=2)["itens"]) == 2
    with pytest.raises(ValueError):
        buscar_contatos(con, "maria", limite=0)


def test_digitos_curtos_nao_casam_telefone(con):
    _google(con, "a@x", TEL, "João")
    assert buscar_contatos(con, "932")["itens"] == []


def test_contatos_buscar_sem_escopo(banco):
    c = conectar(banco)
    tok = emitir(c, "x", ["fin"])
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        assert chamar(cli, tok, "contatos_buscar", texto="ana")["erro"] == "sem_escopo"


def test_contatos_buscar_pelo_servidor(banco):
    c = conectar(banco)
    _google(c, "a@x", TEL, "João Silva")
    tok = emitir(c, "x", ["contatos"])
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        assert chamar(cli, tok, "contatos_buscar", texto="joao")["dados"]["itens"][0]["nome"] == "João Silva"


def test_escopo_hermes():
    assert "contatos" in ESCOPOS_HERMES and ESCOPOS_FERRAMENTAS["contatos_buscar"] == "contatos"
    assert "contatos_buscar" in ferramentas_do_token(ESCOPOS_HERMES)
