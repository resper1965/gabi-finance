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


def test_conciliar_recebimento_pela_api(cli, banco):
    from gabi.db import conectar
    c = conectar(banco)
    c.execute("update empresa set dados=? where id='ness'", (json.dumps({"relacao": "contratante", "email_cobranca": "fin@ness.com.br"}),))
    cred = c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, status) "
                     "values (2,'cred','2026-10-10',10000,'PIX NESS','PIX','ness','posted')").lastrowid
    c.close()
    rid = post(cli, "/api/v1/cobrar/reembolsos", {"empresa_id": "ness"}).json()["dados"]["id"]
    post(cli, f"/api/v1/cobrar/reembolsos/{rid}/cobrado")
    ness = next(e for e in get(cli, "/api/v1/cobrar/reembolsos").json()["dados"]["empresas"] if e["empresa_id"] == "ness")
    assert [x["lancamento_id"] for x in ness["creditos"]] == [cred] and ness["creditos"][0]["a_aplicar"] == "100.00"
    r = post(cli, "/api/v1/cobrar/reembolsos/conciliar", {"empresa_id": "ness", "credito_id": cred})
    assert r.status_code == 200 and r.json()["dados"]["casados"] == [1] and r.json()["dados"]["sobra"] == "0.00"
    ness2 = next(e for e in get(cli, "/api/v1/cobrar/reembolsos").json()["dados"]["empresas"] if e["empresa_id"] == "ness")
    assert ness2["creditos"] == []  # o crédito foi todo aplicado
    assert post(cli, "/api/v1/cobrar/reembolsos/conciliar", {"empresa_id": "ness", "credito_id": 1}).status_code == 400  # lançamento 1 é saída no PF
