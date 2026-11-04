"""Cenário ponta a ponta do canal de decisão, com banco fictício: a API cria a pergunta (boss), o Hermes lê e responde pelo MCP."""

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as McpClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar, rpc  # noqa: F401  (fixtures e helpers)

BOSS = {"Tailscale-User-Login": "boss@x.com"}


@pytest.fixture
def api(banco):
    c = conectar(banco)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.close()
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


@pytest.fixture
def mcp(banco):
    with McpClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        yield c


@pytest.fixture
def toks(banco):
    c = conectar(banco)
    t = {"dec": emitir(c, "hermes", ["decisoes"]), "fin": emitir(c, "so-fin", ["fin"])}
    c.close()
    return t


PERGUNTA = {"tipo": "conta", "titulo": "Itaú PF entra no caixa?", "contexto": "sem decisão há 5 dias",
            "opcoes": [{"n": 1, "rotulo": "Sim, liberar", "efeito": "marcar_conta_sim", "parametros": {"conta_id": 2}},
                       {"n": 2, "rotulo": "Não, tirar", "efeito": "marcar_conta_nao", "parametros": {"conta_id": 2}},
                       {"n": 3, "rotulo": "Deixar para depois", "efeito": "registrar_nota"}]}


def test_fluxo_completo_da_pergunta_a_decisao(api, mcp, toks, banco):
    r = api.post("/api/v1/decisoes/perguntas", headers=BOSS, json=PERGUNTA)
    assert r.status_code == 200, r.text
    pid = r.json()["dados"]["id"]
    ab = chamar(mcp, toks["dec"], "decisoes_abertas")["dados"]["itens"]
    assert [p["id"] for p in ab] == [pid] and [o["n"] for o in ab[0]["opcoes"]] == [1, 2, 3]
    assert all("efeito" not in o and "parametros" not in o for o in ab[0]["opcoes"])  # o canal vê só n e rótulo
    ok = chamar(mcp, toks["dec"], "decisao_responder", pergunta_id=pid, opcao=2)["dados"]
    assert ok["estado"] == "respondida" and ok["escolha"] == 2
    c = conectar(banco)
    assert c.execute("select estado from conta where id=2").fetchone()[0] == "nao"
    d = c.execute("select quem, origem from decisao where origem='canal'").fetchone()
    assert (d["quem"], d["origem"]) == ("ricardo", "canal")
    assert chamar(mcp, toks["dec"], "decisoes_abertas")["dados"]["itens"] == []
    # segunda resposta diferente é recusada e não muda nada
    r2 = chamar(mcp, toks["dec"], "decisao_responder", pergunta_id=pid, opcao=1)
    assert r2["erro"] == "ja_respondida" and c.execute("select estado from conta where id=2").fetchone()[0] == "nao"


def test_token_sem_escopo_decisoes_nao_alcanca(mcp, toks):
    assert chamar(mcp, toks["fin"], "decisoes_abertas")["erro"] == "sem_escopo"
    assert chamar(mcp, toks["fin"], "decisao_responder", pergunta_id=1, opcao=1)["erro"] == "sem_escopo"


def test_o_canal_nao_cria_pergunta_nem_escolhe_efeito(mcp, toks):
    nomes = {t["name"] for t in rpc(mcp, toks["dec"], "tools/list").json()["result"]["tools"]}
    assert {"decisoes_abertas", "decisao_responder"} <= nomes and not {n for n in nomes if "pergunta" in n}


def test_opcao_invalida_pelo_canal_vira_erro_estruturado(api, mcp, toks):
    pid = api.post("/api/v1/decisoes/perguntas", headers=BOSS, json=PERGUNTA).json()["dados"]["id"]
    assert chamar(mcp, toks["dec"], "decisao_responder", pergunta_id=pid, opcao=7)["erro"] == "opcao_invalida"
    assert chamar(mcp, toks["dec"], "decisao_responder", pergunta_id=999, opcao=1)["erro"] == "nao_encontrada"
    assert len(chamar(mcp, toks["dec"], "decisoes_abertas")["dados"]["itens"]) == 1


def test_api_so_para_boss_e_valida_efeito(api):
    assert api.post("/api/v1/decisoes/perguntas", headers={"Tailscale-User-Login": "vip@x.com"}, json=PERGUNTA).status_code == 403
    ruim = {**PERGUNTA, "opcoes": [{"n": 1, "rotulo": "x", "efeito": "apagar_tudo"}]}
    r = api.post("/api/v1/decisoes/perguntas", headers=BOSS, json=ruim)
    assert r.status_code == 400
    assert api.get("/api/v1/decisoes/perguntas", headers=BOSS).json()["dados"]["perguntas"] == []
    api.post("/api/v1/decisoes/perguntas", headers=BOSS, json=PERGUNTA)
    assert len(api.get("/api/v1/decisoes/perguntas?estado=aberta", headers=BOSS).json()["dados"]["perguntas"]) == 1


def test_qualidade_e_duracao_das_chamadas_mcp(api, mcp, toks, banco):
    chamar(mcp, toks["fin"], "financeiro_saldo")
    ms = conectar(banco).execute("select duracao_ms from chamada_mcp where ferramenta='financeiro_saldo'").fetchone()[0]
    assert isinstance(ms, int) and ms >= 0
    q = api.get("/api/v1/gabi/qualidade", headers=BOSS).json()["dados"]
    assert set(q) == {"aceite", "custo", "latencia"} and any(f["ferramenta"] == "financeiro_saldo" for f in q["latencia"]["ferramentas"])
    assert api.get("/api/v1/gabi/qualidade", headers={"Tailscale-User-Login": "vip@x.com"}).status_code == 403
