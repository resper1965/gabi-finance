import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.familia import contato as ct
from gabi.familia import documentos as dc

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
JSON = {"Content-Type": "application/json"}
AGORA = dt.datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
NUM = "111.444.777-09"


@pytest.fixture
def banco(tmp_path):
    b = tmp_path / "g.db"
    c = conectar(b)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into pessoa(id, nome, papel, dados) values ('lia','Lia','filha', ?)", (json.dumps({"apelido": "Lilica"}),))
    c.execute("insert into pessoa_documento(pessoa_id, tipo, pais, numero, validade, paperless_id, origem, criado_em, atualizado_em)"
              " values ('lia','cpf','BR',?,'2026-12-01',7,'carga','2026-10-01','2026-10-01')", (NUM,))
    c.close()
    return b


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def test_listar_fichas_sem_numero(cli):
    r = _get(cli, "/api/v1/familia/fichas")
    assert r.status_code == 200
    assert r.json()["dados"]["itens"][0]["documentos_qtd"] == 1 and "111" not in r.text


def test_ficha_com_numero_e_paperless_url(cli, banco):
    j = _get(cli, "/api/v1/familia/fichas/lia").json()["dados"]
    assert j["paperless_url"] is None and j["documentos"][0]["numero"] == NUM
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('paperless.url', ?)", (json.dumps("http://p.local"),))
    c.close()
    assert _get(cli, "/api/v1/familia/fichas/lia").json()["dados"]["paperless_url"] == "http://p.local"
    assert _get(cli, "/api/v1/familia/fichas/nada").status_code == 404


def _proposta(banco):
    c = conectar(banco)
    pid = dc.propor(c, "lia", tipo="rg", numero="12.345.678-9", origem="hermes", agora=AGORA)
    c.close()
    return pid


def test_propostas_listar_e_decidir(cli, banco):
    pid = _proposta(banco)
    itens = _get(cli, "/api/v1/familia/propostas").json()["dados"]["itens"]
    assert [i["id"] for i in itens] == [pid] and itens[0]["proposto"]["tipo"] == "rg"
    assert _get(cli, "/api/v1/familia/propostas").json()["dados"]["paperless_url"] is None  # base dos links "Paperless #id"
    assert _get(cli, "/api/v1/familia/propostas?estado=x").status_code == 400
    assert _post(cli, f"/api/v1/familia/propostas/{pid}/decisao", {"estado": "talvez"}).status_code == 400
    assert _post(cli, f"/api/v1/familia/propostas/{pid}/decisao", {}).status_code == 400
    r = _post(cli, f"/api/v1/familia/propostas/{pid}/decisao", {"estado": "aprovada"})
    assert r.status_code == 200 and r.json()["dados"]["estado"] == "aprovada"
    assert _post(cli, f"/api/v1/familia/propostas/{pid}/decisao", {"estado": "recusada"}).status_code == 409
    assert _post(cli, "/api/v1/familia/propostas/999/decisao", {"estado": "recusada"}).status_code == 404
    assert conectar(banco).execute("select quem from decisao where origem='familia' order by id desc limit 1").fetchone()[0] == "boss@x.com"


def test_historico_e_desfazer(cli, banco):
    c = conectar(banco)
    h = ct.atualizar(c, "lia", "parentesco", "definir", "filha", "boss@x.com", AGORA)["historico_id"]
    c.close()
    itens = _get(cli, "/api/v1/familia/historico?pessoa=lia").json()["dados"]["itens"]
    assert itens[0]["campo"] == "parentesco" and itens[0]["depois"] == "filha"
    assert _get(cli, "/api/v1/familia/historico?pessoa=outra").json()["dados"]["itens"] == []
    r = _post(cli, f"/api/v1/familia/historico/{h}/desfazer")
    assert r.status_code == 200 and r.json()["dados"]["depois"] is None
    assert _post(cli, f"/api/v1/familia/historico/{h}/desfazer").status_code == 409
    assert _post(cli, "/api/v1/familia/historico/999/desfazer").status_code == 404


def test_vencimentos(cli):
    itens = _get(cli, "/api/v1/familia/vencimentos?meses=3").json()["dados"]["itens"]
    assert itens[0]["tipo"] == "cpf" and itens[0]["validade"] == "2026-12-01" and "numero" not in itens[0]
    assert _get(cli, "/api/v1/familia/vencimentos?meses=0").status_code == 400
    assert _get(cli, "/api/v1/familia/vencimentos?meses=1").json()["dados"]["itens"] == []


@pytest.mark.parametrize("metodo,url", [
    ("GET", "/api/v1/familia/fichas"), ("GET", "/api/v1/familia/fichas/lia"), ("GET", "/api/v1/familia/propostas"),
    ("POST", "/api/v1/familia/propostas/1/decisao"), ("GET", "/api/v1/familia/historico"),
    ("POST", "/api/v1/familia/historico/1/desfazer"), ("GET", "/api/v1/familia/vencimentos")])
def test_nao_boss_403(cli, metodo, url):
    r = cli.request(metodo, url, headers={**VIP, **JSON}, content="{}" if metodo == "POST" else None)
    assert r.status_code == 403
