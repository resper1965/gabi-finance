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


class _GraphForaDoLaco(_Graph):
    """Registra se a chamada ao provedor rodou fora do laço de eventos da API (num thread de trabalho)."""

    def __init__(self):
        super().__init__()
        self.no_laco = None

    def evento_criar(self, conta, chave, conteudo):
        import asyncio
        try:
            asyncio.get_running_loop()
            self.no_laco = True
        except RuntimeError:
            self.no_laco = False
        return super().evento_criar(conta, chave, conteudo)


def test_enviar_roda_fora_do_laco_e_devolve_resultado_do_dominio(banco):
    g = _GraphForaDoLaco()
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"graph_ness": (lambda: g)}), client=("127.0.0.1", 50000))
    _ligar(banco)
    r = _proposta(banco)
    resp = _post(cli, f"/api/v1/envios/{r['id']}/enviar", {"hash": r["hash"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["dados"] == {"id": r["id"], "estado": "enviada"}
    assert g.no_laco is False and len(g.chamadas) == 1
    c = conectar(banco)
    assert tuple(c.execute("select estado, externo_id from envio_proposta where id=?", (r["id"],)).fetchone()) == ("enviada", "ev1")
    c.close()


# ---- convites ----

def _convite(banco, ext="AAMk-1", ini="2026-10-22T18:00:00+00:00", fim="2026-10-22T19:00:00+00:00", titulo="Comitê", resposta="needsAction", org="Ana Souza",
             serie=None):
    c = conectar(banco)
    fonte = c.execute("select id from agenda_fonte where conta=?", (NESS,)).fetchone()[0]
    i = c.execute(
        "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, livre, resposta, organizador_nome, serie_id)"
        " values (?,?,?,?,?,?,0,?,0,?,?,?)", (fonte, ext, ini, fim, ini[:10], fim[:10], titulo, resposta, org, serie)).lastrowid
    c.close()
    return i


def test_convites_lista_com_conflito_e_proposta_id(cli, banco):
    ev = _convite(banco)
    _convite(banco, ext="AAMk-2", titulo="Almoço", resposta="accepted", ini="2026-10-22T18:30:00+00:00", fim="2026-10-22T20:00:00+00:00")
    itens = cli.get("/api/v1/envios/convites", headers=BOSS).json()["dados"]["itens"]
    assert len(itens) == 1
    assert itens[0] == {"evento_id": ev, "conta": NESS, "titulo": "Comitê", "inicio_utc": "2026-10-22T18:00:00+00:00", "fim_utc": "2026-10-22T19:00:00+00:00",
                        "organizador_nome": "Ana Souza", "conflita_com": ["Almoço"], "proposta_id": None}
    r = _post(cli, f"/api/v1/envios/convites/{ev}/propor", {"conta": NESS, "resposta": "aceitar"})
    assert r.status_code == 200, r.text
    itens = cli.get("/api/v1/envios/convites", headers=BOSS).json()["dados"]["itens"]
    assert itens[0]["proposta_id"] == r.json()["dados"]["id"]


def test_convites_serie_uma_linha_e_proposta_id_pela_serie(cli, banco):
    a = _convite(banco, serie="S1")
    b = _convite(banco, ext="AAMk-2", ini="2026-10-23T18:00:00+00:00", fim="2026-10-23T19:00:00+00:00", serie="S1")
    _convite(banco, ext="AAMk-3", ini="2026-10-24T18:00:00+00:00", fim="2026-10-24T19:00:00+00:00", serie="S1")
    itens = cli.get("/api/v1/envios/convites", headers=BOSS).json()["dados"]["itens"]
    assert [i["evento_id"] for i in itens] == [a]
    r = _post(cli, f"/api/v1/envios/convites/{a}/propor", {"conta": NESS, "resposta": "aceitar"})
    assert r.status_code == 200, r.text
    c = conectar(banco)
    c.execute("delete from agenda_evento where id=?", (a,))  # a primeira passou/sumiu: a próxima da série aparece com a mesma proposta aberta
    c.commit()
    c.close()
    itens = cli.get("/api/v1/envios/convites", headers=BOSS).json()["dados"]["itens"]
    assert [(i["evento_id"], i["proposta_id"]) for i in itens] == [(b, r.json()["dados"]["id"])]


def test_convites_propor_cria_proposta_e_duplicada_409(cli, banco):
    ev = _convite(banco)
    r = _post(cli, f"/api/v1/envios/convites/{ev}/propor", {"conta": NESS, "resposta": "talvez"})
    assert r.status_code == 200, r.text
    d = r.json()["dados"]
    assert d["estado"] == "pendente" and d["vence_em"] and d["resumo"]
    assert [i["id"] for i in cli.get("/api/v1/envios", headers=BOSS).json()["dados"]["itens"]] == [d["id"]]
    r2 = _post(cli, f"/api/v1/envios/convites/{ev}/propor", {"conta": NESS, "resposta": "talvez"})
    assert r2.status_code == 409 and r2.json()["erro"] == "proposta_duplicada"


def test_convites_propor_nao_pendente_409(cli, banco):
    ev = _convite(banco, resposta="accepted")
    r = _post(cli, f"/api/v1/envios/convites/{ev}/propor", {"conta": NESS, "resposta": "aceitar"})
    assert r.status_code == 409 and r.json()["erro"] == "convite_nao_pendente"


def test_convites_propor_corpo_invalido_400(cli, banco):
    ev = _convite(banco)
    u = f"/api/v1/envios/convites/{ev}/propor"
    assert _post(cli, u, {"conta": NESS}).status_code == 400
    assert _post(cli, u, {"conta": NESS, "resposta": "x"}).status_code == 400
    assert _post(cli, u, {"resposta": "aceitar"}).status_code == 400


def test_convites_nao_boss_403(cli, banco):
    ev = _convite(banco)
    assert cli.get("/api/v1/envios/convites", headers=VIP).status_code == 403
    assert _post(cli, f"/api/v1/envios/convites/{ev}/propor", {"conta": NESS, "resposta": "aceitar"}, VIP).status_code == 403
