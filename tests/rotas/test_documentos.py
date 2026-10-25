"""Rotas /api/v1/documentos: propostas (listar, aprovar com correção, trocar titular, recusar, 409), titulares, vencimentos e 403.
Consome: gabi.api, gabi.documentos.repositorio, migrações."""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.documentos import repositorio as rep

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
JSON = {"Content-Type": "application/json"}
AGORA = dt.datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
NUM = "FK077009"


def _doc(titular_id="lia", numero=NUM, validade="2030-01-01", titular_tipo="pessoa", tipo="passaporte"):
    return {"titular_tipo": titular_tipo, "titular_id": titular_id, "tipo": tipo, "pais": "BR", "emissor": None,
            "numeros": [{"nome": "numero", "valor": numero}], "datas": [{"tipo": "validade", "data": validade}]}


@pytest.fixture
def banco(tmp_path):
    b = tmp_path / "g.db"
    c = conectar(b)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into pessoa(id, nome, papel, dados) values ('lia','Lia','filha', ?)",
              (json.dumps({"apelido": "Lilica", "telefone": "+5511999990000", "emails": ["lia@x.com"]}),))
    c.execute("insert into pessoa(id, nome, papel, dados) values ('bia','Beatriz','filha','{}')")
    c.execute("insert into bem(id, tipo, nome, dados) values ('carro','veiculo','Carro','{\"modelo\":\"Onix\"}')")
    c.close()
    return b


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def _propor(banco, doc=None, **kw):
    c = conectar(banco)
    base = dict(origem="leitura", paperless_id=31, conferir=True, motivos=["validade antes da emissão"], agora=AGORA)
    base.update(kw)
    pid = rep.propor(c, doc or _doc(), **base)
    c.close()
    return pid


def test_listar_propostas_com_paperless_url(cli, banco):
    pid = _propor(banco)
    j = _get(cli, "/api/v1/documentos/propostas").json()["dados"]
    assert j["paperless_url"] is None and [i["id"] for i in j["itens"]] == [pid]
    it = j["itens"][0]
    assert it["titular"] == {"tipo": "pessoa", "id": "lia", "nome": "Lia"} and it["doc"]["numeros"][0]["valor"] == NUM
    assert it["conferir"] is True and it["motivos"] == ["validade antes da emissão"] and it["paperless_id"] == 31
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('paperless.url', ?)", (json.dumps("http://p.local"),))
    c.close()
    assert _get(cli, "/api/v1/documentos/propostas").json()["dados"]["paperless_url"] == "http://p.local"
    assert _get(cli, "/api/v1/documentos/propostas?estado=aprovada").json()["dados"]["itens"] == []
    assert _get(cli, "/api/v1/documentos/propostas?estado=x").json()["erro"] == "requisicao_invalida"


def test_aprovar_com_correcao_de_campo(cli, banco):
    pid = _propor(banco)
    r = _post(cli, f"/api/v1/documentos/propostas/{pid}/decisao",
              {"estado": "aprovada", "correcao": {"datas": [{"tipo": "validade", "data": "2031-02-03"}]}})
    assert r.status_code == 200 and r.json()["dados"]["estado"] == "aprovada" and r.json()["dados"]["documento_id"]
    c = conectar(banco)
    d = rep.consultar(c, titular_id="lia")
    assert d[0]["datas"] == [{"tipo": "validade", "data": "2031-02-03"}] and d[0]["numeros"][0]["valor"] == NUM
    o_que, quem, origem = c.execute("select o_que, quem, origem from decisao order by id desc limit 1").fetchone()
    assert origem == "documentos" and quem == "boss@x.com" and NUM not in o_que


def test_aprovar_trocando_titular(cli, banco):
    pid = _propor(banco)
    r = _post(cli, f"/api/v1/documentos/propostas/{pid}/decisao", {"estado": "aprovada", "correcao": {"titular_id": "bia"}})
    assert r.status_code == 200
    c = conectar(banco)
    assert [d["titular_id"] for d in rep.consultar(c)] == ["bia"]


def test_correcao_invalida_e_titular_inexistente(cli, banco):
    pid = _propor(banco)
    url = f"/api/v1/documentos/propostas/{pid}/decisao"
    assert _post(cli, url, {"estado": "aprovada", "correcao": "x"}).json()["erro"] == "requisicao_invalida"
    assert _post(cli, url, {"estado": "aprovada", "correcao": {"nada": 1}}).json()["erro"] == "requisicao_invalida"
    r = _post(cli, url, {"estado": "aprovada", "correcao": {"titular_id": "ninguem"}})
    assert r.status_code == 400 and r.json()["erro"] == "titular_invalido"
    r = _post(cli, url, {"estado": "aprovada", "correcao": {"datas": [{"tipo": "validade", "data": "2031-13-40"}]}})
    assert r.status_code == 400 and r.json()["erro"] == "valor_invalido" and "2031" not in r.text
    assert _post(cli, url, {}).status_code == 400
    assert _post(cli, url, {"estado": "talvez"}).status_code == 400


def test_recusar_e_409_em_decisao_repetida(cli, banco):
    pid = _propor(banco)
    url = f"/api/v1/documentos/propostas/{pid}/decisao"
    r = _post(cli, url, {"estado": "recusada"})
    assert r.status_code == 200 and r.json()["dados"]["documento_id"] is None
    assert rep.consultar(conectar(banco)) == []
    r = _post(cli, url, {"estado": "aprovada"})
    assert r.status_code == 409 and r.json()["erro"] == "conflito"
    assert _post(cli, "/api/v1/documentos/propostas/999/decisao", {"estado": "recusada"}).status_code == 404


def test_titulares_com_documentos_e_contato(cli, banco):
    _post(cli, f"/api/v1/documentos/propostas/{_propor(banco)}/decisao", {"estado": "aprovada"})
    pid = _propor(banco, _doc("carro", "ABC1D23", "2027-01-31", "bem", "crlv"))
    _post(cli, f"/api/v1/documentos/propostas/{pid}/decisao", {"estado": "aprovada"})
    j = _get(cli, "/api/v1/documentos/titulares").json()["dados"]
    lia = next(p for p in j["pessoas"] if p["id"] == "lia")
    assert lia["apelido"] == "Lilica" and lia["telefones"] == ["+5511999990000"] and lia["emails"] == ["lia@x.com"]
    assert [d["numeros"][0]["valor"] for d in lia["documentos"]] == [NUM]
    assert next(p for p in j["pessoas"] if p["id"] == "bia")["documentos"] == []
    assert j["bens"] == [{"id": "carro", "tipo": "veiculo", "nome": "Carro", "dados": {"modelo": "Onix"},
                          "documentos": [j["bens"][0]["documentos"][0]]}]
    assert j["bens"][0]["documentos"][0]["numeros"][0]["valor"] == "ABC1D23" and j["paperless_url"] is None


def test_vencimentos(cli, banco):
    _post(cli, f"/api/v1/documentos/propostas/{_propor(banco, _doc(validade='2026-12-01'))}/decisao", {"estado": "aprovada"})
    itens = _get(cli, "/api/v1/documentos/vencimentos?meses=3").json()["dados"]["itens"]
    assert [(i["titular_id"], i["tipo"], i["data"], i["vencido"]) for i in itens] == [("lia", "passaporte", "2026-12-01", False)]
    assert _get(cli, "/api/v1/documentos/vencimentos?meses=1").json()["dados"]["itens"] == []
    assert _get(cli, "/api/v1/documentos/vencimentos?meses=0").status_code == 400


@pytest.mark.parametrize("metodo,url", [
    ("GET", "/api/v1/documentos/propostas"), ("POST", "/api/v1/documentos/propostas/1/decisao"),
    ("GET", "/api/v1/documentos/titulares"), ("GET", "/api/v1/documentos/vencimentos")])
def test_nao_boss_403(cli, metodo, url):
    r = cli.request(metodo, url, headers={**VIP, **JSON}, content="{}" if metodo == "POST" else None)
    assert r.status_code == 403


def test_vencimentos_usa_a_data_de_brasilia(banco):
    """U5: 22h de 22/10 em Brasília já é 23/10 em UTC; o vencimento de 22/10 ainda não venceu."""
    agora = dt.datetime(2026, 10, 23, 1, 0, tzinfo=dt.timezone.utc)
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: agora), client=("127.0.0.1", 50000))
    _post(cli, f"/api/v1/documentos/propostas/{_propor(banco, _doc(validade='2026-10-22'))}/decisao", {"estado": "aprovada"})
    itens = _get(cli, "/api/v1/documentos/vencimentos?meses=3").json()["dados"]["itens"]
    assert [(i["data"], i["vencido"]) for i in itens] == [("2026-10-22", False)]
