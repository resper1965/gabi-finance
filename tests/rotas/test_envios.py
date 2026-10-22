import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.envios import propostas as p

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
JSON = {"Content-Type": "application/json"}
AGORA = dt.datetime(2026, 10, 22, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
NESS = "resper@ness.com.br"


class _Graph:
    def __init__(self):
        self.chamadas = []

    def evento_criar(self, conta, chave, conteudo):
        self.chamadas.append((conta, chave))
        return {"externo_id": "ev1"}


@pytest.fixture
def banco(tmp_path):
    b = tmp_path / "g.db"
    c = conectar(b)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?)", (json.dumps([NESS]),))
    c.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values (?,?, 'primary','sim')", (NESS, "graph"))
    c.close()
    return b


@pytest.fixture
def graph():
    return _Graph()


@pytest.fixture
def cli(banco, graph):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"graph_ness": (lambda: graph)}), client=("127.0.0.1", 50000))


def _ligar(banco):
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('envios.escrita', ?) on conflict(chave) do update set valor=excluded.valor", (json.dumps("ligado"),))
    c.close()


def _proposta(banco):
    c = conectar(banco)
    r = p.criar_evento(c, AGORA, conta=NESS, titulo="Reunião", inicio="2026-10-23T15:00", duracao_min=60, convidados=["ana@x.com"])
    h = c.execute("select hash from envio_proposta where id=?", (r["id"],)).fetchone()[0]
    c.close()
    return {"id": r["id"], "hash": h}


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def test_listar_pendentes_com_conteudo_e_escrita(cli, banco):
    r = _proposta(banco)
    j = cli.get("/api/v1/envios", headers=BOSS).json()["dados"]
    assert j["escrita"] == "desligado"
    assert [i["id"] for i in j["itens"]] == [r["id"]]
    assert j["itens"][0]["conteudo"]["titulo"] == "Reunião"
    _ligar(banco)
    assert cli.get("/api/v1/envios", headers=BOSS).json()["dados"]["escrita"] == "ligado"


def test_estado_invalido_400(cli):
    assert cli.get("/api/v1/envios?estado=x", headers=BOSS).status_code == 400


def test_enviar_ok(cli, banco, graph):
    _ligar(banco)
    r = _proposta(banco)
    resp = _post(cli, f"/api/v1/envios/{r['id']}/enviar", {"hash": r["hash"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["dados"] == {"id": r["id"], "estado": "enviada"}
    assert len(graph.chamadas) == 1


def test_enviar_sem_hash_400(cli, banco):
    _ligar(banco)
    r = _proposta(banco)
    assert _post(cli, f"/api/v1/envios/{r['id']}/enviar", {}).status_code == 400


def test_enviar_hash_errado_409(cli, banco, graph):
    _ligar(banco)
    r = _proposta(banco)
    resp = _post(cli, f"/api/v1/envios/{r['id']}/enviar", {"hash": "x"})
    assert resp.status_code == 409 and resp.json()["erro"] == "hash_diferente"
    assert graph.chamadas == []


def test_enviar_desligado_409_sem_chamar(cli, banco, graph):
    r = _proposta(banco)
    resp = _post(cli, f"/api/v1/envios/{r['id']}/enviar", {"hash": r["hash"]})
    assert resp.status_code == 409 and resp.json()["erro"] == "envios_desligados"
    assert graph.chamadas == []


def test_recusar(cli, banco):
    r = _proposta(banco)
    resp = _post(cli, f"/api/v1/envios/{r['id']}/recusar")
    assert resp.status_code == 200 and resp.json()["dados"] == {"id": r["id"], "estado": "recusada"}
    assert _post(cli, f"/api/v1/envios/{r['id']}/recusar").status_code == 409


def test_nao_encontrado_404(cli):
    assert _post(cli, "/api/v1/envios/999/recusar").status_code == 404
    assert _post(cli, "/api/v1/envios/999/enviar", {"hash": "x"}).status_code == 404


def test_nao_boss_403(cli, banco):
    r = _proposta(banco)
    assert cli.get("/api/v1/envios", headers=VIP).status_code == 403
    assert _post(cli, f"/api/v1/envios/{r['id']}/enviar", {"hash": r["hash"]}, VIP).status_code == 403
    assert _post(cli, f"/api/v1/envios/{r['id']}/recusar", h=VIP).status_code == 403
