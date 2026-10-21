import datetime as dt
import json
from zoneinfo import ZoneInfo

from tests.rotas.test_cobrar_api import BOSS, JSON, VIP, banco, cli, get, nibo, post  # noqa: F401  (fixtures e helpers)


def patch(cli, url, corpo, h=BOSS):
    return cli.patch(url, headers={**h, **JSON}, content=json.dumps(corpo))


def put(cli, url, corpo, h=BOSS):
    return cli.put(url, headers={**h, **JSON}, content=json.dumps(corpo))


def test_categoria_aceita_e_devolve_o_id_equivalente_no_nibo(cli):
    r = post(cli, "/api/v1/cadastros/categorias", {"nome": "Viagem", "nibo_category_id": "cat-viagem"})
    assert r.status_code == 201 and r.json()["dados"]["nibo_category_id"] == "cat-viagem"
    cid = r.json()["dados"]["id"]
    assert patch(cli, f"/api/v1/cadastros/categorias/{cid}", {"nibo_category_id": "cat-2"}).json()["dados"]["nibo_category_id"] == "cat-2"
    assert patch(cli, f"/api/v1/cadastros/categorias/{cid}", {"nibo_category_id": None}).json()["dados"]["nibo_category_id"] is None


def test_socio_do_nibo_define_e_le(cli):
    assert get(cli, "/api/v1/cadastros/nibo").json()["dados"]["socio_id"] == "socio"  # da fixture
    assert put(cli, "/api/v1/cadastros/nibo", {"socio_id": "novo-socio"}).status_code == 200
    assert get(cli, "/api/v1/cadastros/nibo").json()["dados"]["socio_id"] == "novo-socio"
    assert put(cli, "/api/v1/cadastros/nibo", {"socio_id": "  "}).status_code == 400
    assert put(cli, "/api/v1/cadastros/nibo", {"socio_id": "x"}, VIP).status_code == 403
