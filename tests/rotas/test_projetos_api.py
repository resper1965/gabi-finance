"""API /api/v1/projetos e /api/v1/anexos: cada rota só chama gabi.projetos (hoje = 08/10/2026 nas fixtures de test_cadastros_api)."""
import pytest

from gabi.db import conectar
from tests.rotas.test_cadastros_api import BOSS, VIP, banco, cli, req  # noqa: F401  (fixtures do cliente HTTP)

U = "/api/v1/projetos"


def _criar(cli, nome="Carro", **extra):
    r = req(cli, "POST", U, {"nome": nome, **extra})
    assert r.status_code == 201, r.text
    return r.json()["dados"]


@pytest.fixture(autouse=True)
def _anexos_dir(tmp_path, monkeypatch):
    d = tmp_path / "anexos"
    d.mkdir()
    monkeypatch.setenv("ANEXOS_DIR", str(d))
    return d


def test_vip_nao_acessa(cli):
    for metodo, url in (("GET", U), ("POST", U), ("GET", f"{U}/1"), ("PATCH", f"{U}/1"), ("POST", f"{U}/1/pessoas"), ("POST", f"{U}/1/gastos"),
                        ("POST", f"{U}/1/fatos"), ("POST", f"{U}/1/anexos"), ("GET", "/api/v1/anexos/recentes"), ("GET", "/api/v1/anexos/1/arquivo")):
        assert req(cli, metodo, url, {} if metodo != "GET" else None, h=VIP).status_code == 403, (metodo, url)


def test_criar_com_atividades_e_ver(cli):
    p = _criar(cli, objetivo="trocar o motor", orcamento="5.000,00", atividades=[{"texto": "orçamento"}, {"texto": "aprovar", "depois_de": 1}])
    assert p["nome"] == "Carro" and p["orcamento"] == "5000.00" and p["saldo"] == "5000.00" and p["progresso"] == {"feitas": 0, "total": 2}
    assert [a["texto"] for a in p["proximas"]] == ["orçamento"] and [a["texto"] for a in p["bloqueadas"]] == ["aprovar"]
    assert req(cli, "GET", f"{U}/{p['id']}").json()["dados"]["objetivo"] == "trocar o motor"
    itens = req(cli, "GET", U).json()["dados"]["itens"]
    assert [i["id"] for i in itens] == [p["id"]] and itens[0]["progresso"] == {"feitas": 0, "total": 2}
    assert req(cli, "GET", f"{U}?status=pausado").json()["dados"]["itens"] == []


def test_status_invalido_e_campo_desconhecido_e_dado_ruim_sao_400(cli):
    assert req(cli, "GET", f"{U}?status=lixo").status_code == 400
    assert req(cli, "POST", U, {"nome": "X", "cor": "azul"}).status_code == 400
    assert req(cli, "POST", U, {"nome": ""}).status_code == 400
    assert req(cli, "POST", U, {"nome": "X", "orcamento": "abc"}).status_code == 400
    assert req(cli, "POST", U, {"nome": "X", "atividades": [{"texto": "a", "depois_de": 1}]}).status_code == 400
    assert conectar(cli.app.state.banco).execute("select count(*) from projeto").fetchone()[0] == 0
    p = _criar(cli)
    assert req(cli, "PATCH", f"{U}/{p['id']}", {"status": "lixo"}).status_code == 400
    assert req(cli, "PATCH", f"{U}/{p['id']}", {"foo": 1}).status_code == 400


def test_patch_status_final_e_reabrir_400(cli):
    p = _criar(cli)
    r = req(cli, "PATCH", f"{U}/{p['id']}", {"status": "concluido", "prazo": "2026-12-01", "nome": "Carro azul", "objetivo": "ok", "orcamento": "100,00"})
    assert r.status_code == 200 and r.json()["dados"]["status"] == "concluido" and r.json()["dados"]["nome"] == "Carro azul" and r.json()["dados"]["orcamento"] == "100.00"
    assert req(cli, "PATCH", f"{U}/{p['id']}", {"status": "ativo"}).status_code == 400
    assert req(cli, "GET", f"{U}?status=concluido").json()["dados"]["itens"][0]["id"] == p["id"]


def test_pessoa_gasto_e_fato_gravam_decisao_do_painel(cli, banco):
    p = _criar(cli, orcamento="1000,00")
    base = f"{U}/{p['id']}"
    assert req(cli, "POST", f"{base}/pessoas", {"nome": "Seu Jorge", "papel": "mecânico"}).status_code == 201
    g = req(cli, "POST", f"{base}/gastos", {"valor": "150,25", "descricao": "peça"})
    assert g.status_code == 201 and g.json()["dados"]["valor"] == "150.25"
    c = conectar(banco)
    c.execute("insert into lancamento(id, conta_id, externo_id, data, valor_centavos) values (7, 1, 'e7', '2026-10-01', -20000)")
    assert req(cli, "POST", f"{base}/gastos", {"lancamento_id": 7}).status_code == 201
    f = req(cli, "POST", f"{base}/fatos", {"texto": "Prazo é dia 20", "data": "2026-10-07", "pessoa_nome": "Seu Jorge"})
    assert f.status_code == 201 and f.json()["dados"]["data"] == "2026-10-07"
    v = req(cli, "GET", base).json()["dados"]
    assert v["gasto"] == "350.25" and v["saldo"] == "649.75" and [x["nome"] for x in v["pessoas"]] == ["Seu Jorge"] and v["fatos_recentes"][0]["texto"] == "Prazo é dia 20"
    quem = {tuple(r) for r in c.execute("select quem, origem from decisao where o_que like 'projeto%'")}
    assert quem == {("boss@x.com", "painel")}
    assert c.execute("select count(*) from decisao where o_que like 'projeto%'").fetchone()[0] == 5


def test_gasto_e_fato_invalidos_400(cli):
    p = _criar(cli)
    base = f"{U}/{p['id']}"
    assert req(cli, "POST", f"{base}/gastos", {}).status_code == 400
    assert req(cli, "POST", f"{base}/gastos", {"valor": "1,00", "lancamento_id": 1}).status_code == 400
    assert req(cli, "POST", f"{base}/gastos", {"valor": "1.500"}).status_code == 400  # ambíguo
    assert req(cli, "POST", f"{base}/gastos", {"lancamento_id": 999}).status_code == 400
    assert req(cli, "POST", f"{base}/fatos", {"texto": ""}).status_code == 400
    assert req(cli, "POST", f"{base}/fatos", {"texto": "x", "anexo_id": "um"}).status_code == 400


def test_id_inexistente_e_404(cli):
    for metodo, url, corpo in (("GET", f"{U}/999", None), ("PATCH", f"{U}/999", {"nome": "x"}), ("POST", f"{U}/999/pessoas", {"nome": "x"}),
                               ("POST", f"{U}/999/gastos", {"valor": "1,00"}), ("POST", f"{U}/999/fatos", {"texto": "x"}), ("POST", f"{U}/999/anexos", {"anexo_id": 1}),
                               ("GET", "/api/v1/anexos/999/arquivo", None)):
        assert req(cli, metodo, url, corpo).status_code == 404, (metodo, url)


def _anexo(banco, tipo="imagem", arquivo="ab/ab12.jpg", sha="ab12"):
    c = conectar(banco)
    return c.execute("insert into anexo(tipo, arquivo, sha256, recebido_em) values (?,?,?,'2026-10-07T12:00:00+00:00')", (tipo, arquivo, sha)).lastrowid


def test_caixa_de_entrada_e_ligar_anexo(cli, banco):
    p = _criar(cli)
    a = _anexo(banco)
    assert [x["id"] for x in req(cli, "GET", "/api/v1/anexos/recentes").json()["dados"]["itens"]] == [a]
    r = req(cli, "POST", f"{U}/{p['id']}/anexos", {"anexo_id": a})
    assert r.status_code == 201 and r.json()["dados"]["projeto_id"] == p["id"]
    assert req(cli, "GET", "/api/v1/anexos/recentes").json()["dados"]["itens"] == []
    d = req(cli, "POST", f"{U}/{p['id']}/anexos", {"paperless_id": 55})
    assert d.json()["dados"]["tipo"] == "documento" and req(cli, "GET", f"{U}/{p['id']}").json()["dados"]["anexos"] == 2
    assert req(cli, "POST", f"{U}/{p['id']}/anexos", {}).status_code == 400


def test_arquivo_devolve_os_bytes_e_o_tipo_certo(cli, banco, _anexos_dir):
    (_anexos_dir / "ab").mkdir()
    (_anexos_dir / "ab" / "ab12.jpg").write_bytes(b"\xff\xd8fotinha")
    (_anexos_dir / "ab" / "cd34.ogg").write_bytes(b"OggS")
    a, b = _anexo(banco), _anexo(banco, "audio", "ab/cd34.ogg", "cd34")
    r = req(cli, "GET", f"/api/v1/anexos/{a}/arquivo")
    assert r.status_code == 200 and r.content == b"\xff\xd8fotinha" and r.headers["content-type"] == "image/jpeg"
    assert req(cli, "GET", f"/api/v1/anexos/{b}/arquivo").headers["content-type"].startswith("audio/")


def test_arquivo_sumido_ou_documento_ou_fora_da_pasta_e_404(cli, banco):
    sumido = _anexo(banco)
    fora = _anexo(banco, arquivo="../../etc/passwd", sha="zz")
    doc = conectar(banco).execute("insert into anexo(tipo, paperless_id, recebido_em) values ('documento', 5, 'x')").lastrowid
    for i in (sumido, fora, doc):
        assert req(cli, "GET", f"/api/v1/anexos/{i}/arquivo").status_code == 404
