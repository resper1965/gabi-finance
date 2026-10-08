import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada

MIGRACOES = Path(__file__).parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    con = conectar(p)
    migrar(con, MIGRACOES)
    adicionar(con, "boss@x.com", "p1", "boss", por="t")
    adicionar(con, "vip@x.com", "p2", "familia_vip", por="t")
    con.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco), client=("127.0.0.1", 50000))


def test_eu_devolve_identidade(cli):
    r = cli.get("/api/eu", headers=VIP)
    assert r.status_code == 200 and r.json() == {"login": "vip@x.com", "pessoa_id": "p2", "nivel": "familia_vip"}


def test_erro_segue_formato_pt_br(cli):
    r = cli.get("/api/eu")
    assert r.status_code == 401 and set(r.json()) == {"erro", "mensagem"}
    assert cli.get("/api/saude", headers=VIP).json()["erro"] == "sem_escopo"


def test_saude_exige_boss_e_traz_estado(cli, banco):
    assert cli.get("/api/saude", headers=VIP).status_code == 403
    con = conectar(banco)
    with registrar_rodada(con, "teste") as r:
        r.lidos = 3
    d = cli.get("/api/saude", headers=BOSS).json()
    assert d["db"] == "ok" and d["schema"] == 1
    assert d["ultima_rodada"]["fonte"] == "teste" and d["ultima_rodada"]["status"] == "ok"
    assert d["tabelas"]["acesso"] == 2 and "memoria" in d["tabelas"]


def test_seguranca_lista_acessos_e_contagens(cli, banco):
    con = conectar(banco)
    con.execute("insert into token_agente(nome, escopo, hash, criado_em) values ('hermes','fin','h1','2026-10-08')")
    con.execute("insert into token_agente(nome, escopo, hash, criado_em, revogado_em) values ('velho','fin','h2','2026-10-01','2026-10-02')")
    cli.get("/api/eu", headers=BOSS)  # a própria chamada só é registrada após responder
    d = cli.get("/api/seguranca", headers=BOSS).json()
    assert [a["login"] for a in d["acessos"]] == ["boss@x.com", "vip@x.com"]
    assert d["tokens_ativos"] == 1 and d["ultimo_backup"] is None
    assert d["chamadas_24h"] == 1


def test_toda_chamada_api_e_registrada_inclusive_recusadas(cli, banco):
    cli.get("/api/eu")                          # 401
    cli.get("/api/saude", headers=VIP)          # 403
    cli.get("/api/eu", headers=BOSS)            # 200
    con = conectar(banco)
    linhas = [(r["metodo"], r["caminho"], r["status"], r["login"]) for r in con.execute(
        "select metodo, caminho, status, login from chamada order by id")]
    assert linhas == [("GET", "/api/eu", 401, None), ("GET", "/api/saude", 403, "vip@x.com"),
                      ("GET", "/api/eu", 200, "boss@x.com")]


def test_revogar_tudo_sem_confirmo_400_e_nada_muda(cli, banco):
    con = conectar(banco)
    con.execute("insert into token_agente(nome, escopo, hash, criado_em) values ('h','fin','h1','2026-10-08')")
    for corpo in (None, {}, {"confirmo": False}):
        r = cli.post("/api/revogar-tudo", headers=BOSS, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 400 and r.json()["erro"] == "confirmacao_ausente"
    assert con.execute("select count(*) from token_agente where revogado_em is null").fetchone()[0] == 1


@pytest.mark.parametrize("valor", ["true", 1, "sim", [True]])
def test_revogar_tudo_com_confirmo_nao_booleano_400(cli, valor):
    assert cli.post("/api/revogar-tudo", headers=BOSS, json={"confirmo": valor}).status_code == 400


def test_revogar_tudo_exige_boss(cli):
    assert cli.post("/api/revogar-tudo", headers=VIP, json={"confirmo": True}).status_code == 403


def test_revogar_tudo_ok_revoga_e_registra_decisao(cli, banco):
    con = conectar(banco)
    for i in range(2):
        con.execute("insert into token_agente(nome, escopo, hash, criado_em) values (?, 'fin', ?, '2026-10-08')", (f"t{i}", f"h{i}"))
    r = cli.post("/api/revogar-tudo", headers=BOSS, json={"confirmo": True})
    assert r.status_code == 200 and r.json() == {"revogados": 2}
    assert con.execute("select count(*) from token_agente where revogado_em is null").fetchone()[0] == 0
    d = con.execute("select quem, o_que from decisao order by id desc limit 1").fetchone()
    assert d["quem"] == "boss@x.com" and "revogar" in d["o_que"].lower()


def test_raiz_serve_html_com_design_do_sistema(cli):
    r = cli.get("/", headers=BOSS)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert 'href="/static/industry.css"' in r.text and "blueprint" in r.text and 'class="table"' in r.text
    assert "googleapis" not in r.text and "cdn" not in r.text.lower()
    assert cli.get("/").status_code == 401  # a página também exige identidade


def test_css_do_sistema_e_servido(cli):
    assert cli.get("/static/industry.css").status_code == 200


def test_industry_css_identico_ao_do_prototipo():
    orig = (Path(__file__).parent / "fixtures" / "industry.original.css").read_text(encoding="utf-8")
    copia = (Path(__file__).parent.parent / "gabi" / "static" / "industry.css").read_text(encoding="utf-8")
    sem_import = "\n".join(l for l in orig.splitlines() if not l.lstrip().startswith("@import url("))
    assert copia.strip() == sem_import.strip()
