import datetime as dt

from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import ESCOPOS_HERMES, criar_mcp
from tests.rotas.test_cadastros_api import AGORA, BOSS, VIP, banco, cli, req  # noqa: F401

HOST = "127.0.0.1:8081"
U = "/api/v1/agentes"


def dados(r):
    return r.json()["dados"]


def _criar(cli, corpo=None):
    r = req(cli, "POST", U, corpo or {"nome": "Agente"})
    assert r.status_code == 201, r.text
    return dados(r)


def _mcp(banco, chave, metodo="tools/list", params=None):
    app = criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA)
    with TestClient(app, base_url=f"http://{HOST}") as c:
        h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "Host": HOST, "Authorization": f"Bearer {chave}"}
        corpo = {"jsonrpc": "2.0", "id": 1, "method": metodo, **({"params": params} if params else {})}
        return c.post("/mcp", headers=h, json=corpo)


def test_vip_nao_acessa(cli):
    assert req(cli, "GET", U, h=VIP).status_code == 403
    assert req(cli, "POST", U, {"nome": "x"}, h=VIP).status_code == 403


def test_criar_devolve_chave_e_listar_nao(cli):
    d = _criar(cli)
    assert d["chave"].startswith("gb_") and d["nome"] == "Agente"
    r = req(cli, "GET", U)
    assert d["chave"] not in r.text and "chave" not in r.text and "hash" not in r.text
    assert [i["id"] for i in dados(r)["itens"]] == [d["id"]]


def test_criar_sem_escopos_usa_padrao_do_hermes_sem_sensivel(cli):
    d = _criar(cli)
    assert sorted(d["escopos"]) == sorted(ESCOPOS_HERMES) and "sensivel" not in d["escopos"]


def test_nome_vazio_400(cli):
    assert req(cli, "POST", U, {"nome": "  "}).status_code == 400
    assert req(cli, "POST", U, {}).status_code == 400


def test_escopo_invalido_400(cli):
    assert req(cli, "POST", U, {"nome": "x", "escopos": ["xyz"]}).status_code == 400
    assert req(cli, "POST", U, {"nome": "x", "escopos": "fin"}).status_code == 400


def test_campo_desconhecido_400(cli):
    assert req(cli, "POST", U, {"nome": "x", "foo": 1}).status_code == 400
    d = _criar(cli)
    assert req(cli, "PATCH", f"{U}/{d['id']}/escopos", {"escopos": ["fin"], "foo": 1}).status_code == 400


def test_patch_escopos_e_404_em_revogada(cli):
    d = _criar(cli)
    r = req(cli, "PATCH", f"{U}/{d['id']}/escopos", {"escopos": ["fin"]})
    assert r.status_code == 200 and dados(r)["escopos"] == ["fin"] and "chave" not in r.text
    assert req(cli, "POST", f"{U}/{d['id']}/revogar").status_code == 200
    assert req(cli, "PATCH", f"{U}/{d['id']}/escopos", {"escopos": ["fin"]}).status_code == 404


def test_revogar_e_rotacionar(cli, banco):
    a = _criar(cli)
    b = _criar(cli, {"nome": "Outro"})
    assert _mcp(banco, a["chave"]).status_code == 200
    r = req(cli, "POST", f"{U}/{a['id']}/rotacionar")
    assert r.status_code == 200
    nova = dados(r)
    assert nova["chave"] != a["chave"] and nova["id"] != a["id"] and nova["nome"] == "Agente"
    r1 = _mcp(banco, a["chave"])
    assert r1.status_code == 401 and "nao_autenticado" in r1.text
    assert _mcp(banco, nova["chave"]).status_code == 200
    r = req(cli, "POST", f"{U}/{b['id']}/revogar")
    assert r.status_code == 200 and dados(r)["revogado_em"] and "chave" not in r.text
    assert _mcp(banco, b["chave"]).status_code == 401
    assert req(cli, "POST", f"{U}/{a['id']}/rotacionar").status_code == 404


def test_id_inexistente_404(cli):
    assert req(cli, "POST", f"{U}/999/revogar").status_code == 404
    assert req(cli, "POST", f"{U}/999/rotacionar").status_code == 404
    assert req(cli, "GET", f"{U}/999/chamadas").status_code == 404
    assert req(cli, "PATCH", f"{U}/999/escopos", {"escopos": ["fin"]}).status_code == 404


def test_chamadas_traz_ferramenta_status_quando_sem_argumentos(cli, banco):
    d = _criar(cli)
    r = _mcp(banco, d["chave"], "tools/call", {"name": "financeiro_saldo", "arguments": {}})
    assert r.status_code == 200
    r = req(cli, "GET", f"{U}/{d['id']}/chamadas")
    it = dados(r)["itens"]
    assert it and set(it[0]) == {"quando", "ferramenta", "status"} and it[0]["ferramenta"] == "financeiro_saldo"


def test_uso_aparece_na_listagem_via_mcp_real(cli, banco):
    d = _criar(cli)
    assert dados(req(cli, "GET", U))["itens"][0]["ultimo_uso"] is None
    for _ in range(2):
        assert _mcp(banco, d["chave"], "tools/call", {"name": "financeiro_saldo", "arguments": {}}).status_code == 200
    item = dados(req(cli, "GET", U))["itens"][0]
    assert item["chamadas_7d"] == 2
    # quando é ISO UTC: o ultimo_uso do GET tem que ser o mesmo valor gravado
    assert dt.datetime.fromisoformat(item["ultimo_uso"]).utcoffset() == dt.timedelta(0)


def test_conexao_devolve_url_padrao(cli):
    d = dados(req(cli, "GET", f"{U}/conexao"))
    assert d["url"].endswith("/mcp") and "fin" in d["escopos_validos"] and d["escopos_padrao"] == list(ESCOPOS_HERMES)


def test_decisao_gravada_com_login_do_painel(cli, banco):
    d = _criar(cli)
    req(cli, "POST", f"{U}/{d['id']}/rotacionar")
    c = conectar(banco)
    rows = c.execute("select quem, o_que, origem from decisao where origem='agentes'").fetchall()
    c.close()
    assert len(rows) == 2 and all(r["quem"] == "boss@x.com" for r in rows)
    assert not any(d["chave"] in r["o_que"] or "gb_" in r["o_que"] for r in rows)
