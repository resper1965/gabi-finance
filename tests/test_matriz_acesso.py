"""T4.4: a matriz de acesso vale por rota. Familiar e terceiro nunca alcançam as rotas do boss; o que a matriz libera, só no grau liberado."""
import re
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.identidade import Identidade, exigir_informacao, grau

MIGRACOES = Path(__file__).parent.parent / "migrations"
LOGINS = {"boss": "boss@x.com", "familia_vip": "mae@x.com", "terceiros": "ext@x.com"}
MATRIZ = {"saúde": ("total", "parcial", "nenhum"), "caixa": ("total", "nenhum", "nenhum"), "agenda": ("total", "total", "parcial")}


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    con = conectar(p)
    migrar(con, MIGRACOES)
    for nivel, login in LOGINS.items():
        adicionar(con, login, "p1", nivel, por="teste")
    for info, (b, f, t) in MATRIZ.items():
        con.execute("insert into matriz_acesso(informacao, boss, familia_vip, terceiros) values (?,?,?,?)", (info, b, f, t))
    con.close()
    return p


def _chamar(app, login, metodo, caminho):
    return TestClient(app, client=("127.0.0.1", 50000)).request(metodo, caminho, headers={"Tailscale-User-Login": login})


def test_grau_le_a_matriz_e_sem_linha_so_o_boss_ve(banco):
    con = conectar(banco)
    assert grau(con, "saúde", "familia_vip") == "parcial" and grau(con, "caixa", "familia_vip") == "nenhum"
    assert grau(con, "inexistente", "boss") == "total"
    assert grau(con, "inexistente", "familia_vip") == "nenhum" and grau(con, "inexistente", "terceiros") == "nenhum"


@pytest.mark.parametrize("informacao,nivel,esperado", [(i, n, g) for i, graus in MATRIZ.items() for n, g in zip(LOGINS, graus)])
def test_rota_por_informacao_segue_a_matriz_celula_a_celula(banco, informacao, nivel, esperado):
    app = FastAPI()
    app.state.banco, app.state.permite_tcp_local = banco, True

    @app.get("/x")
    def x(i: Identidade = Depends(exigir_informacao(informacao))):
        return {"grau": grau(conectar(banco), informacao, i.nivel)}

    r = _chamar(app, LOGINS[nivel], "GET", "/x")
    if esperado == "nenhum":
        assert r.status_code == 403
    else:
        assert r.status_code == 200 and r.json()["grau"] == esperado


def test_grau_total_exigido_barra_o_parcial(banco):
    app = FastAPI()
    app.state.banco, app.state.permite_tcp_local = banco, True

    @app.get("/x")
    def x(i: Identidade = Depends(exigir_informacao("saúde", "total"))):
        return {}

    assert _chamar(app, LOGINS["familia_vip"], "GET", "/x").status_code == 403
    assert _chamar(app, LOGINS["boss"], "GET", "/x").status_code == 200


def test_nenhuma_rota_do_app_real_abre_para_familiar_ou_terceiro_alem_do_publico(banco):
    app = criar_app(banco, permite_tcp_local=True)
    rotas = [(m.upper(), p) for p, ops in app.openapi()["paths"].items() if p.startswith("/api") for m in ops]  # openapi enxerga as rotas dos routers incluídos
    assert len(rotas) > 60, "varredura curta demais: as rotas dos routers sumiram do openapi"  # 67 depois do corte (eram mais de 80 com as áreas que saíram)
    abertas = set()
    for metodo, caminho in rotas:
        url = re.sub(r"\{[^}]+\}", "1", caminho)
        for nivel in ("familia_vip", "terceiros"):
            if _chamar(app, LOGINS[nivel], metodo, url).status_code not in (401, 403):
                abertas.add((metodo, caminho, nivel))
    # rotas que pedem só 'terceiros' ou a matriz (saúde parcial): qualquer abertura nova precisa entrar aqui de propósito
    esperadas = {("GET", "/api/eu", "familia_vip"), ("GET", "/api/eu", "terceiros")}
    familia = {(m, c, "familia_vip") for m, c, _ in abertas if c.startswith("/api/v1/familia/") and m == "GET"}
    assert abertas - familia == esperadas, sorted(abertas - familia - esperadas)
