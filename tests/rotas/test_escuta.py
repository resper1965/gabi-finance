import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
JSON = {"Content-Type": "application/json"}
AGORA = dt.datetime(2026, 10, 16, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
N = "+5511912345678"
NQ = "%2B5511912345678"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-16T11:00:00+00:00','2026-10-16T11:01:00+00:00','ok',1)")
    c.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def _pendente(banco, numero=N, nome="Joana"):
    c = conectar(banco)
    c.execute("insert into escuta_remetente(numero, nome, estado, vista_em, qtd) values (?,?, 'pendente', '2026-10-16T10:00:00+00:00', 2)", (numero, nome))
    c.close()


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _put(cli, corpo, h=BOSS):
    return cli.put("/api/v1/escuta/parametros", headers={**h, **JSON}, content=json.dumps(corpo))


def _decisoes(banco):
    c = conectar(banco)
    r = [x["o_que"] for x in c.execute("select o_que from decisao order by id")]
    c.close()
    return r


def test_so_boss_acessa(cli):
    for url in ("/api/v1/escuta/remetentes", "/api/v1/escuta/grupos", "/api/v1/escuta/parametros"):
        assert cli.get(url, headers=VIP).status_code == 403
        assert cli.get(url).status_code == 401
        assert cli.get(url, headers=BOSS).status_code == 200
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "familia"}, VIP).status_code == 403
    assert cli.post(f"/api/v1/escuta/remetentes/{NQ}/ignorar", content="{}", headers=JSON).status_code == 401
    assert _put(cli, {"modo": "ativo"}, VIP).status_code == 403


def test_aprovar_sem_papel_ou_papel_invalido_400(cli, banco):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {}).status_code == 400
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "chefe"}).status_code == 400
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "familia", "nome": 3}).status_code == 400


def test_numero_que_nao_normaliza_404_ou_400(cli):
    assert _post(cli, "/api/v1/escuta/remetentes/123/aprovar", {"papel": "familia"}).status_code in (400, 404)
    assert _post(cli, "/api/v1/escuta/remetentes/abc/ignorar").status_code in (400, 404)


def test_aprovar_move_da_fila_para_aprovados(cli, banco):
    _pendente(banco)
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert [f["numero"] for f in d["fila"]] == [N] and d["aprovados"] == []
    r = _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "prestador", "nome": "Joana Silva"})
    assert r.status_code == 200
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert d["fila"] == []
    assert len(d["aprovados"]) == 1
    a = d["aprovados"][0]
    assert a["numero"] == N and a["papel"] == "prestador" and a["nome"] == "Joana Silva" and a["pessoa_id"]
    assert sum("aprovou" in o for o in _decisoes(banco)) == 1  # auditado uma vez só


@pytest.mark.parametrize("seg", ["%2B5511912345678", "5511912345678", "+5511912345678", "11912345678", "%2B55%2011%2091234-5678"])
def test_numero_em_formatos_diferentes_e_o_mesmo_remetente(cli, banco, seg):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{seg}/aprovar", {"papel": "familia"}).status_code == 200
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert [a["numero"] for a in d["aprovados"]] == [N]
    c = conectar(banco)
    assert c.execute("select count(*) from escuta_remetente").fetchone()[0] == 1
    c.close()


@pytest.mark.parametrize("acao,estado", [("ignorar", "ignorado"), ("bloquear", "bloqueado")])
def test_ignorar_e_bloquear(cli, banco, acao, estado):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/{acao}").status_code == 200
    c = conectar(banco)
    assert c.execute("select estado from escuta_remetente where numero=?", (N,)).fetchone()[0] == estado
    c.close()
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert d["fila"] == [] and d["aprovados"] == []
    assert any(estado in o for o in _decisoes(banco))


def test_ignorar_nao_toca_no_spool(cli, banco, tmp_path):
    spool = tmp_path / "spool"
    (spool / "anexos").mkdir(parents=True)
    anexo = spool / "anexos" / "a.pdf"
    anexo.write_bytes(b"x")
    _pendente(banco)
    c = conectar(banco)
    c.execute("insert into escuta_msg(id_externo, de, grupo, recebida_em, anexo_caminho) values ('1',?,0,'2026-10-16T10:00:00+00:00',?)", (N, str(anexo)))
    c.close()
    antes = sorted(p.name for p in spool.rglob("*"))
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/ignorar").status_code == 200
    assert anexo.exists() and sorted(p.name for p in spool.rglob("*")) == antes
    c = conectar(banco)
    assert c.execute("select anexo_caminho from escuta_msg").fetchone()[0] is None
    c.close()


def test_grupos_listar_e_aprovar_404(cli, banco):
    c = conectar(banco)
    c.execute("insert into escuta_grupo(id_grupo, nome) values ('g1@g.us','Escola')")
    c.close()
    g = cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"]
    assert g == [{"id_grupo": "g1@g.us", "nome": "Escola", "aprovado": False}]
    assert _post(cli, "/api/v1/escuta/grupos/g1@g.us/aprovar").status_code == 200
    assert cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"][0]["aprovado"] is True
    assert any("g1@g.us" in o for o in _decisoes(banco))
    assert _post(cli, "/api/v1/escuta/grupos/nao-existe/aprovar").status_code == 404


def test_parametros_padrao_quando_nao_definidos(cli):
    p = cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]
    assert p["modo"] == "registro" and p["palavras_risco"] == [] and p["horas_sem_receber"] == 12 and p["anexo_max_mb"] == 25


def test_parametros_validam_modo(cli):
    assert _put(cli, {"modo": "outro"}).status_code == 400
    assert _put(cli, {"modo": 1}).status_code == 400
    assert _put(cli, {"modo": "ativo"}).status_code == 200
    assert cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]["modo"] == "ativo"


@pytest.mark.parametrize("corpo", [
    {"palavras_risco": "x"}, {"palavras_risco": [""]}, {"palavras_risco": ["a", 3]}, {"palavras_risco": ["x" * 61]},
    {"palavras_risco": ["a"] * 201}, {"palavras_risco": ["  "]},
    {"horas_sem_receber": 0}, {"horas_sem_receber": 169}, {"horas_sem_receber": 1.5}, {"horas_sem_receber": True}, {"horas_sem_receber": "3"},
    {"anexo_max_mb": 0}, {"anexo_max_mb": 101}, {"anexo_max_mb": None},
    {"desconhecido": 1}, {},
])
def test_parametros_invalidos_400(cli, corpo):
    assert _put(cli, corpo).status_code == 400


def test_parametros_validos_e_auditoria_sem_palavras(cli, banco):
    r = _put(cli, {"palavras_risco": ["me matar", "sumir"], "horas_sem_receber": 24, "anexo_max_mb": 10, "modo": "ativo"})
    assert r.status_code == 200
    p = cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]
    assert p == {"modo": "ativo", "palavras_risco": ["me matar", "sumir"], "horas_sem_receber": 24, "anexo_max_mb": 10}
    c = conectar(banco)
    assert json.loads(c.execute("select valor from parametro where chave='escuta.horas_sem_receber'").fetchone()[0]) == 24
    assert _put(cli, {"horas_sem_receber": 1, "anexo_max_mb": 100}).status_code == 200
    linhas = c.execute("select quem, o_que, origem from decisao where origem='escuta'").fetchall()
    c.close()
    assert len(linhas) == 2 and all(x["quem"] == "boss@x.com" for x in linhas)
    todo = " ".join(x["o_que"] for x in linhas)
    assert "palavras_risco" in todo and "me matar" not in todo and "sumir" not in todo
