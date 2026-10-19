import json

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar

from tests.rotas.test_escuta import AGORA, BOSS, JSON, VIP, banco  # noqa: F401  (fixture banco)

U = "/api/v1/teams/fontes"


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def _post(cli, corpo, h=BOSS):
    return cli.post(U, headers={**h, **JSON}, content=json.dumps(corpo))


def _put(cli, fid, corpo, h=BOSS):
    return cli.put(f"{U}/{fid}/estado", headers={**h, **JSON}, content=json.dumps(corpo))


def _decisoes(banco):
    c = conectar(banco)
    r = [(x["o_que"], x["origem"]) for x in c.execute("select o_que, origem from decisao where origem='teams' order by id")]
    c.close()
    return r


def test_lista_vazia(cli):
    r = cli.get(U, headers=BOSS)
    assert r.status_code == 200
    assert r.json()["dados"]["fontes"] == []


def test_criar_a_decidir(cli, banco):
    r = _post(cli, {"conta": "Resper@Ness.com.br"})
    assert r.status_code == 201, r.text
    fid = r.json()["dados"]["id"]
    f = cli.get(U, headers=BOSS).json()["dados"]["fontes"]
    assert [(x["id"], x["conta"], x["estado"]) for x in f] == [(fid, "resper@ness.com.br", "a_decidir")]
    d = _decisoes(banco)
    assert d == [(f"teams: cadastrou fonte {fid}", "teams")]
    assert "ness.com.br" not in d[0][0]


def test_estado_muda_e_audita_sem_conta(cli, banco):
    fid = _post(cli, {"conta": "a@b.com"}).json()["dados"]["id"]
    r = _put(cli, fid, {"estado": "sim"})
    assert r.status_code == 200 and r.json()["dados"] == {"id": fid, "estado": "sim"}
    assert cli.get(U, headers=BOSS).json()["dados"]["fontes"][0]["estado"] == "sim"
    assert _decisoes(banco)[-1] == (f"teams: fonte {fid} -> sim", "teams")


@pytest.mark.parametrize("corpo", [{}, {"conta": "nao-e-email"}, {"conta": 5}])
def test_conta_invalida_400(cli, corpo):
    assert _post(cli, corpo).status_code == 400


def test_duplicada_409(cli):
    assert _post(cli, {"conta": "a@b.com"}).status_code == 201
    assert _post(cli, {"conta": "A@B.com"}).status_code == 409


def test_estado_invalido_400(cli):
    fid = _post(cli, {"conta": "a@b.com"}).json()["dados"]["id"]
    assert _put(cli, fid, {"estado": "talvez"}).status_code == 400
    assert _put(cli, fid, {}).status_code == 400


def test_estado_inexistente_404(cli):
    assert _put(cli, 999, {"estado": "sim"}).status_code == 404


def test_so_boss(cli):
    for m, url in (("get", U), ("post", U), ("put", f"{U}/1/estado")):
        assert getattr(cli, m)(url, headers=VIP).status_code == 403, (m, url)
