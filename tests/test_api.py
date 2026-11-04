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
    return TestClient(criar_app(banco, permite_tcp_local=True), client=("127.0.0.1", 50000))


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
    assert d["db"] == "ok" and d["schema"] == len(list(MIGRACOES.glob("*.sql")))
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


def test_revogar_tudo_atomico(cli, banco):
    con = conectar(banco)
    for i in range(2):
        con.execute("insert into token_agente(nome, escopo, hash, criado_em) values (?, 'fin', ?, '2026-10-08')", (f"t{i}", f"h{i}"))
    con.execute("create trigger falha_decisao before insert on decisao begin select raise(abort, 'falha simulada'); end")
    with pytest.raises(Exception):
        cli.post("/api/revogar-tudo", headers=BOSS, json={"confirmo": True})
    assert con.execute("select count(*) from token_agente where revogado_em is null").fetchone()[0] == 2


def test_raiz_serve_html_com_design_do_sistema(banco, monkeypatch, tmp_path):
    import gabi.api as api
    monkeypatch.setattr(api, "PAINEL", tmp_path / "sem-build")  # sem build do painel: página de verificação da Fase 0
    cli = TestClient(criar_app(banco, permite_tcp_local=True), client=("127.0.0.1", 50000))
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


# ---- correções da revisão da Fase 0 ----
def test_post_com_content_type_diferente_de_json_415(cli):
    r = cli.post("/api/revogar-tudo", headers={**BOSS, "Content-Type": "text/plain"}, content='{"confirmo": true}')
    assert r.status_code == 415 and r.json()["erro"] == "tipo_invalido"


@pytest.mark.parametrize("cabecalhos", [
    {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}, {"Origin": "https://evil.example"},
])
def test_post_cross_site_recusado_e_nada_muda(cli, banco, cabecalhos):
    con = conectar(banco)
    con.execute("insert into token_agente(nome, escopo, hash, criado_em) values ('h','fin','h1','2026-10-08')")
    r = cli.post("/api/revogar-tudo", headers={**BOSS, **cabecalhos}, json={"confirmo": True})
    assert r.status_code == 403 and r.json()["erro"] == "nao_permitido"
    assert con.execute("select count(*) from token_agente where revogado_em is null").fetchone()[0] == 1


def test_post_same_origin_e_cliente_sem_origin_passam(cli):
    ok1 = cli.post("/api/revogar-tudo", headers={**BOSS, "Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}, json={"confirmo": True})
    ok2 = cli.post("/api/revogar-tudo", headers=BOSS, json={"confirmo": True})
    assert ok1.status_code == 200 and ok2.status_code == 200


def test_erro_500_e_registrado_no_log(banco):
    app = criar_app(banco, permite_tcp_local=True)

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("falha interna")

    c = TestClient(app, client=("127.0.0.1", 50000), raise_server_exceptions=False)
    assert c.get("/api/boom", headers=BOSS).status_code == 500
    r = conectar(banco).execute("select metodo, caminho, status from chamada").fetchone()
    assert tuple(r) == ("GET", "/api/boom", 500)


def test_falha_no_log_nao_troca_a_resposta(banco, monkeypatch):
    import gabi.api as api
    monkeypatch.setattr(api, "_gravar_chamada", lambda *a, **k: (_ for _ in ()).throw(OSError("log indisponível")))
    c = TestClient(criar_app(banco, permite_tcp_local=True), client=("127.0.0.1", 50000))
    assert c.get("/api/eu", headers=BOSS).status_code == 200


def test_raiz_serve_o_painel_compilado_quando_existe(banco, monkeypatch, tmp_path):
    import gabi.api as api
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>PAINEL-REACT</html>")
    (tmp_path / "assets" / "a.js").write_text("console.log(1)")
    monkeypatch.setattr(api, "PAINEL", tmp_path)
    c = TestClient(criar_app(banco, permite_tcp_local=True), client=("127.0.0.1", 50000))
    assert "PAINEL-REACT" in c.get("/", headers=BOSS).text
    assert c.get("/assets/a.js").status_code == 200
    assert c.get("/").status_code == 401


PUBLICA = "https://gabi.exemplo.ts.net"


def _cli_publico(banco):
    app = criar_app(banco, permite_tcp_local=True, origens_confiaveis=[PUBLICA])
    return TestClient(app, client=("127.0.0.1", 50000))


def test_origem_publica_confiavel_passa_mesmo_com_host_interno(banco):
    """Atrás do tailscale serve o Host chega como o do upstream, não o nome público."""
    r = _cli_publico(banco).post("/api/revogar-tudo", headers={**BOSS, "Origin": PUBLICA, "Sec-Fetch-Site": "same-origin"}, json={"confirmo": True})
    assert r.status_code == 200


def test_origem_fora_da_lista_continua_recusada(banco):
    c = _cli_publico(banco)
    for origem in ("https://evil.example", "http://gabi.exemplo.ts.net"):
        r = c.post("/api/revogar-tudo", headers={**BOSS, "Origin": origem}, json={"confirmo": True})
        assert r.status_code == 403 and r.json()["erro"] == "nao_permitido"
    r = c.post("/api/revogar-tudo", headers={**BOSS, "Origin": PUBLICA, "Sec-Fetch-Site": "cross-site"}, json={"confirmo": True})
    assert r.status_code == 403
