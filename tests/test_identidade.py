from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gabi.acesso import adicionar, listar
from gabi.db import conectar, migrar
from gabi.identidade import Identidade, exigir, nivel_suficiente, normalizar_login, resolver

MIGRACOES = Path(__file__).parent.parent / "migrations"
LOGIN = "Resper@Ionic.Health"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    con = conectar(p)
    migrar(con, MIGRACOES)
    adicionar(con, "resper@ionic.health", "p1", "boss", por="teste")
    adicionar(con, "mae@familia.com", "p2", "familia_vip", por="teste")
    con.close()
    return p


def _cliente(banco, host="127.0.0.1"):
    app = FastAPI()
    app.state.banco = banco
    app.state.permite_tcp_local = True  # os testes usam TCP simulado; em produção só socket Unix

    @app.get("/qualquer")
    def qualquer(i: Identidade = Depends(exigir("terceiros"))):
        return {"login": i.login, "nivel": i.nivel}

    @app.get("/so-boss")
    def so_boss(i: Identidade = Depends(exigir("boss"))):
        return {"ok": True}

    return TestClient(app, client=(host, 50000))


def test_login_normalizado(banco):
    assert normalizar_login("  Resper@Ionic.Health ") == "resper@ionic.health"
    con = conectar(banco)
    ident = resolver(con, " Resper@Ionic.Health ")
    assert ident == Identidade(login="resper@ionic.health", pessoa_id="p1", nivel="boss")


def test_resolver_vazio_ou_desconhecido_devolve_none(banco):
    con = conectar(banco)
    assert resolver(con, None) is None and resolver(con, "   ") is None
    assert resolver(con, "estranho@x.com") is None


def test_sem_cabecalho_401(banco):
    assert _cliente(banco).get("/qualquer").status_code == 401


def test_login_desconhecido_403(banco):
    r = _cliente(banco).get("/qualquer", headers={"Tailscale-User-Login": "estranho@x.com"})
    assert r.status_code == 403


@pytest.mark.parametrize("host", ["10.0.0.5", "147.93.2.17", "testclient"])
def test_cabecalho_forjado_de_host_nao_local_403(banco, host):
    r = _cliente(banco, host).get("/qualquer", headers={"Tailscale-User-Login": LOGIN})
    assert r.status_code == 403


def test_host_ipv6_local_e_aceito(banco):
    r = _cliente(banco, "::1").get("/qualquer", headers={"Tailscale-User-Login": LOGIN})
    assert r.status_code == 200


def test_nivel_insuficiente_403(banco):
    r = _cliente(banco).get("/so-boss", headers={"Tailscale-User-Login": "mae@familia.com"})
    assert r.status_code == 403


def test_nivel_ok_200_e_login_com_caixa_diferente(banco):
    r = _cliente(banco).get("/so-boss", headers={"Tailscale-User-Login": LOGIN})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_nivel_suficiente_ordem():
    assert nivel_suficiente("boss", "terceiros") and nivel_suficiente("boss", "boss")
    assert not nivel_suficiente("terceiros", "familia_vip")


def test_adicionar_grava_decisao_e_listar_mostra(banco):
    con = conectar(banco)
    adicionar(con, "Novo@X.com ", "p3", "terceiros", por="cli")
    d = con.execute("select quem, o_que from decisao order by id desc limit 1").fetchone()
    assert d["quem"] == "cli" and "novo@x.com" in d["o_que"] and "terceiros" in d["o_que"]
    assert "novo@x.com" in [a["login"] for a in listar(con)]


def test_adicionar_nivel_invalido_levanta(banco):
    con = conectar(banco)
    with pytest.raises(ValueError):
        adicionar(con, "a@x.com", "p1", "root", por="cli")


def _req(banco, scope_extra, permite_tcp=False, login=LOGIN):
    from starlette.requests import Request
    app = FastAPI()
    app.state.banco = banco
    app.state.permite_tcp_local = permite_tcp
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [(b"tailscale-user-login", login.encode())],
             "app": app, "query_string": b"", **scope_extra}
    return Request(scope)


def test_socket_unix_e_confiavel_mesmo_sem_tcp_local(banco):
    r = _req(banco, {"client": None, "server": ("/run/gabi-brain/api.sock", None)})
    assert exigir("boss")(r).login == "resper@ionic.health"


def test_tcp_local_recusado_quando_producao(banco):
    from fastapi import HTTPException
    r = _req(banco, {"client": ("127.0.0.1", 5000), "server": ("127.0.0.1", 8080)}, permite_tcp=False)
    with pytest.raises(HTTPException) as e:
        exigir("terceiros")(r)
    assert e.value.status_code == 403


def test_tcp_local_aceito_so_quando_permitido(banco):
    r = _req(banco, {"client": ("127.0.0.1", 5000), "server": ("127.0.0.1", 8080)}, permite_tcp=True)
    assert exigir("terceiros")(r).nivel == "boss"


def test_cliente_ausente_em_tcp_nao_e_confiavel(banco):
    from fastapi import HTTPException
    r = _req(banco, {"client": None, "server": ("10.0.0.1", 8080)}, permite_tcp=True)
    with pytest.raises(HTTPException):
        exigir("terceiros")(r)


def test_criar_app_padrao_e_producao_recusa_tcp(banco):
    from gabi.api import criar_app
    c = TestClient(criar_app(banco), client=("127.0.0.1", 50000))
    assert c.get("/api/eu", headers={"Tailscale-User-Login": LOGIN}).status_code == 403
