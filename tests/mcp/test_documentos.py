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
