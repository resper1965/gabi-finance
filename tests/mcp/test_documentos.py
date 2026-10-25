"""Ferramentas documentos_buscar (trecho e referência) e documentos_texto (OCR do Paperless). Sem rede."""
import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.paperless import ErroPaperless, Paperless
from gabi.mcp.ferramentas_prop import _trecho
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.cobrar.paperless_falso import PaperlessFalso
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

LONGO = "x" * 400 + " Passaporte da Lia " + "y" * 400


def _cliente(banco, http):
    app = criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA, paperless=Paperless("http://p", "tok", http=http))
    return TestClient(app, base_url=f"http://{HOST}")


@pytest.fixture
def token(banco):
    c = conectar(banco)
    t = emitir(c, "docs", ["docs"])
    c.close()
    return t


@pytest.fixture
def cli(banco):
    docs = [{"id": 5, "title": "Doc longo", "created": "2026-10-01", "tags": [], "content": LONGO},
            {"id": 6, "title": "Doc curto", "created": "2026-10-02", "tags": [], "content": "ENEL conta de luz"}]
    with _cliente(banco, PaperlessFalso(docs=docs)) as c:
        yield c


def test_trecho_centrado_na_primeira_ocorrencia_sem_diferenca_de_caixa(cli, token):
    itens = chamar(cli, token, "documentos_buscar", texto="PASSAPORTE")["dados"]["itens"]
    d = next(i for i in itens if i["id"] == 5)
    assert len(d["trecho"]) <= 300 and "Passaporte" in d["trecho"]
    assert not d["trecho"].startswith("x" * 300)
    assert d["referencia"] == {"paperless_id": 5, "titulo": "Doc longo", "criado_em": "2026-10-01"}
    assert d["titulo"] == "Doc longo" and d["criado_em"] == "2026-10-01"


def test_trecho_do_comeco_quando_o_termo_nao_aparece(cli, token):
    itens = chamar(cli, token, "documentos_buscar", texto="inexistente")["dados"]["itens"]
    por_id = {i["id"]: i for i in itens}
    assert por_id[5]["trecho"] == LONGO[:300]
    assert por_id[6]["trecho"] == "ENEL conta de luz"


def test_documentos_texto_corta_e_marca_cortado(cli, token):
    d = chamar(cli, token, "documentos_texto", id=5, limite=100)["dados"]
    assert d["texto"] == LONGO[:100] and d["cortado"] is True
    assert d["referencia"] == {"paperless_id": 5, "titulo": "Doc longo", "criado_em": "2026-10-01"}
    inteiro = chamar(cli, token, "documentos_texto", id=6)["dados"]
    assert inteiro["texto"] == "ENEL conta de luz" and inteiro["cortado"] is False


def test_documentos_texto_referencia_vem_do_proprio_documento(cli, token):
    d = chamar(cli, token, "documentos_texto", id=6)["dados"]
    assert d["referencia"] == {"paperless_id": 6, "titulo": "Doc curto", "criado_em": "2026-10-02"}


def test_documentos_texto_id_inexistente_e_nao_encontrado(cli, token):
    assert chamar(cli, token, "documentos_texto", id=999)["erro"] == "nao_encontrado"


def test_trecho_com_termo_no_fim_do_texto():
    t = "a" * 500 + "FIM"
    r = _trecho(t, "fim")
    assert len(r) == 300 and r.endswith("FIM")


def test_trecho_com_termo_maior_que_o_limite():
    termo = "z" * 350
    assert _trecho("ab" + termo + "cd", termo) == "z" * 300  # começa no termo, nunca passa de 300


def test_documentos_texto_limite_fora_da_faixa(cli, token):
    assert "erro" in chamar(cli, token, "documentos_texto", id=5, limite=0)
    assert "erro" in chamar(cli, token, "documentos_texto", id=5, limite=20001)


def test_documentos_texto_exige_escopo_docs(banco, cli):
    c = conectar(banco)
    outro = emitir(c, "fin", ["fin"])
    c.close()
    assert chamar(cli, outro, "documentos_texto", id=5)["erro"] == "sem_escopo"


def test_paperless_fora_do_ar_da_fonte_indisponivel(banco, token):
    def fora(*a, **k):
        raise ErroPaperless("Paperless indisponível: OSError")
    with _cliente(banco, fora) as c:
        assert chamar(c, token, "documentos_texto", id=5)["erro"] == "fonte_indisponivel"


# ---------------- documentos aprovados (escopo `familia`): documentos_consultar, documentos_vencimentos, bens_listar ----------------
import json  # noqa: E402

from tests.mcp.test_servidor import rpc  # noqa: E402

PASS_LOUISE = "YB654321"
RENAVAM = "00987654321"
PLACA = "ABC1D23"
DOCS_FAMILIA = {"documentos_consultar", "documentos_vencimentos", "bens_listar"}


def _doc(c, titular_tipo, titular_id, tipo, numeros, datas=(), paperless_id=None, excluido_em=None) -> int:
    i = c.execute("insert into documento(titular_tipo, titular_id, tipo, pais, paperless_id, origem, criado_em, atualizado_em, excluido_em)"
                  " values (?,?,?,'BR',?,'ricardo','2026-10-01T00:00:00Z','2026-10-01T00:00:00Z',?)",
                  (titular_tipo, titular_id, tipo, paperless_id, excluido_em)).lastrowid
    for n, v in numeros:
        c.execute("insert into documento_numero(documento_id, nome, valor) values (?,?,?)", (i, n, v))
    for t, d in datas:
        c.execute("insert into documento_data(documento_id, tipo, data) values (?,?,?)", (i, t, d))
    return i


@pytest.fixture
def bancod(banco):
    c = conectar(banco)
    c.execute("insert into pessoa(id, nome, dados) values ('louise','Louise Lavrik Esper','{}')")
    c.execute("insert into bem(id, tipo, nome, dados) values ('carro','veiculo','Carro Honda',?)", (json.dumps({"placa": PLACA}),))
    _doc(c, "pessoa", "louise", "passaporte", [("numero", PASS_LOUISE)], [("validade", "2027-01-10")], paperless_id=42)
    _doc(c, "bem", "carro", "crlv", [("renavam", RENAVAM), ("placa", PLACA)], [("vencimento", "2026-11-30")])
    _doc(c, "pessoa", "louise", "rg", [("numero", "SAIU-123")], excluido_em="2026-10-02T00:00:00Z")
    c.execute("insert into parametro(chave, valor) values ('painel.url', ?)", (json.dumps("https://painel.x/"),))
    c.execute("insert into parametro(chave, valor) values ('paperless.url', ?)", (json.dumps("https://pl.x/"),))
    c.close()
    return banco


@pytest.fixture
def tokd(bancod):
    c = conectar(bancod)
    t = {k: emitir(c, k, [k]) for k in ("familia", "fin")}
    c.close()
    return t


@pytest.fixture
def clid(bancod):
    with TestClient(criar_mcp(bancod, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        yield c


def _auditoria(banco) -> list[str]:
    return [r["o_que"] for r in conectar(banco).execute("select o_que from decisao where origem='documentos' order by id")]


def test_consultar_por_titular_resolvido_como_a_familia_devolve_numeros_e_link(clid, tokd, bancod):
    d = chamar(clid, tokd["familia"], "documentos_consultar", titular="Louise")["dados"]
    [doc] = d["itens"]
    assert (doc["titular_nome"], doc["tipo"], doc["numeros"]) == ("Louise Lavrik Esper", "passaporte", [{"nome": "numero", "valor": PASS_LOUISE}])
    assert doc["datas"] == [{"tipo": "validade", "data": "2027-01-10"}]
    assert doc["paperless_link"] == "https://pl.x/documents/42/details"
    assert d["link"] == "https://painel.x/#cadastros/documentos"


def test_consultar_por_bem_e_por_tipo(clid, tokd):
    [doc] = chamar(clid, tokd["familia"], "documentos_consultar", titular="carro honda")["dados"]["itens"]
    assert doc["tipo"] == "crlv" and doc["numeros"][0] == {"nome": "renavam", "valor": RENAVAM}
    [doc] = chamar(clid, tokd["familia"], "documentos_consultar", tipo="CRLV")["dados"]["itens"]
    assert doc["titular_id"] == "carro" and doc["paperless_link"] is None


def test_consultar_por_texto_renavam(clid, tokd):
    [doc] = chamar(clid, tokd["familia"], "documentos_consultar", texto="renavam")["dados"]["itens"]
    assert doc["tipo"] == "crlv" and RENAVAM in json.dumps(doc)


def test_consultar_sem_filtro_traz_os_ativos_e_nunca_o_excluido(clid, tokd):
    r = chamar(clid, tokd["familia"], "documentos_consultar")
    assert {d["tipo"] for d in r["dados"]["itens"]} == {"passaporte", "crlv"} and "SAIU-123" not in json.dumps(r)


def test_consultar_titular_desconhecido_ou_ambiguo(clid, tokd, bancod):
    r = chamar(clid, tokd["familia"], "documentos_consultar", titular="Zé")
    assert r["erro"] == "titular_ambiguo" and "nenhum" in r["mensagem"]
    c = conectar(bancod)
    c.execute("insert into pessoa(id, nome, dados) values ('lu','Louise Maria','{}')")
    r = chamar(clid, tokd["familia"], "documentos_consultar", titular="Louise")
    assert r["erro"] == "titular_ambiguo" and "Louise Maria" in r["mensagem"] and "Louise Lavrik Esper" in r["mensagem"]
    assert _auditoria(bancod) == []


def test_consultar_tipo_invalido(clid, tokd):
    assert chamar(clid, tokd["familia"], "documentos_consultar", tipo="12!")["erro"] == "valor_invalido"


def test_consultar_audita_sem_numero_nem_texto_buscado(clid, tokd, bancod):
    chamar(clid, tokd["familia"], "documentos_consultar", titular="Louise")
    chamar(clid, tokd["familia"], "documentos_consultar", texto=RENAVAM)
    a = _auditoria(bancod)
    assert len(a) == 2 and "louise" in a[0] and "passaporte" in a[0] and "crlv" in a[1]
    tudo = json.dumps(a) + json.dumps([dict(r) for r in conectar(bancod).execute("select * from chamada_mcp")])
    assert PASS_LOUISE not in tudo and RENAVAM not in tudo and PLACA not in tudo
    assert conectar(bancod).execute("select quem from decisao where origem='documentos'").fetchone()["quem"] == "hermes"


def test_vencimentos_por_data_sem_numero(clid, tokd):
    r = chamar(clid, tokd["familia"], "documentos_vencimentos", meses=6)
    d = r["dados"]
    assert d["meses"] == 6 and [(i["titular_nome"], i["tipo"], i["data_tipo"], i["data"]) for i in d["itens"]] == [
        ("Carro Honda", "crlv", "vencimento", "2026-11-30"), ("Louise Lavrik Esper", "passaporte", "validade", "2027-01-10")]
    assert RENAVAM not in json.dumps(r) and PASS_LOUISE not in json.dumps(r)
    assert chamar(clid, tokd["familia"], "documentos_vencimentos", meses=1)["dados"]["itens"] == []


@pytest.mark.parametrize("meses", [0, 121, -1])
def test_vencimentos_meses_fora_da_faixa(clid, tokd, meses):
    assert chamar(clid, tokd["familia"], "documentos_vencimentos", meses=meses)["erro"] == "requisicao_invalida"


def test_bens_listar(clid, tokd):
    [b] = chamar(clid, tokd["familia"], "bens_listar")["dados"]["itens"]
    assert (b["id"], b["tipo"], b["nome"], b["dados"]) == ("carro", "veiculo", "Carro Honda", {"placa": PLACA})


@pytest.mark.parametrize("nome,args", [("documentos_consultar", {"titular": "Louise"}), ("documentos_vencimentos", {}), ("bens_listar", {})])
def test_sem_escopo_familia(clid, tokd, bancod, nome, args):
    assert chamar(clid, tokd["fin"], nome, **args)["erro"] == "sem_escopo"
    assert _auditoria(bancod) == []


def test_docstrings_avisam_dado_de_terceiros(clid, tokd):
    desc = {t["name"]: t["description"] for t in rpc(clid, tokd["familia"], "tools/list").json()["result"]["tools"]}
    for n in DOCS_FAMILIA:
        assert "dado de terceiros" in desc[n], n
