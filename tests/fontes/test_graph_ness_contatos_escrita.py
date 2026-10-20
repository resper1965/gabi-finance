import json
from pathlib import Path

import pytest

from gabi.fontes import graph_ness as g
from gabi.fontes import graph_ness_contatos as gc
from gabi.fontes.graph_ness import ErroGraphNess, GraphNess
from tests.fontes.test_graph_ness import TokenFalso, _graph

CONTA = "resper@ness.com.br"
GID = "AAMkAGI2TG93AAA="
URL = f"https://graph.microsoft.com/v1.0/users/resper%40ness.com.br/contacts"
ANTES = {"nome": "Ana Souza", "telefone": "(11) 98888-7777"}
DEPOIS = {"nome": "Ana Souza Lima", "telefone": "+5511988887777"}


def test_criar_faz_post_so_com_displayname_e_mobilephone():
    gr, http = _graph([(201, {"id": GID})])
    assert gr.contato_criar(CONTA, "Ana", "+5511988887777") == {"id": GID}
    (metodo, url, corpo, cab), = http.chamadas
    assert (metodo, url) == ("POST", URL)
    assert json.loads(corpo) == {"displayName": "Ana", "mobilePhone": "+5511988887777"}
    assert cab["Authorization"] == "Bearer TOK1"


def test_criar_resposta_sem_id_valido():
    gr, _ = _graph([(201, {"id": "a b"})])
    with pytest.raises(ErroGraphNess, match="resposta inválida do Graph"):
        gr.contato_criar(CONTA, "Ana", "123")


def test_erro_http_sem_corpo_nem_dados():
    gr, _ = _graph([(500, {"error": "Ana 999"})])
    with pytest.raises(ErroGraphNess) as e:
        gr.contato_criar(CONTA, "Ana", "999")
    assert str(e.value) == "contato: HTTP 500"


def test_corrigir_so_patch_apos_reler_sem_mudanca():
    gr, http = _graph([(200, {"displayName": ANTES["nome"], "mobilePhone": ANTES["telefone"]}), (200, {})])
    assert gr.contato_corrigir(CONTA, GID, ANTES, DEPOIS) == {"resultado": "ok"}
    leitura, escrita = http.chamadas
    assert leitura[0] == "GET" and leitura[1] == f"{URL}/AAMkAGI2TG93AAA%3D?$select=displayName,mobilePhone"
    assert escrita[0] == "PATCH" and escrita[1] == f"{URL}/AAMkAGI2TG93AAA%3D"
    assert json.loads(escrita[2]) == {"displayName": DEPOIS["nome"], "mobilePhone": DEPOIS["telefone"]}


@pytest.mark.parametrize("relida", [{"displayName": "Outro", "mobilePhone": ANTES["telefone"]},
                                    {"displayName": ANTES["nome"], "mobilePhone": "000"},
                                    {"displayName": ANTES["nome"]}])
def test_corrigir_contato_alterado_nao_escreve(relida):
    gr, http = _graph([(200, relida)])
    assert gr.contato_corrigir(CONTA, GID, ANTES, DEPOIS) == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


def test_conta_fora_da_lista_recusada_sem_http():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.contato_criar("x@y.com", "Ana", "1")
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.contato_corrigir("x@y.com", GID, ANTES, DEPOIS)
    assert http.chamadas == []


@pytest.mark.parametrize("gid", ["../x", "a b", "", None, "curto"])
def test_id_invalido_recusado(gid):
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="id de contato inválido"):
        gr.contato_corrigir(CONTA, gid, ANTES, DEPOIS)
    assert http.chamadas == []


def test_401_invalida_token_e_repete_uma_vez():
    tok = TokenFalso()
    gr, http = _graph([(401, {}), (201, {"id": GID})], token=tok)
    assert gr.contato_criar(CONTA, "Ana", "1") == {"id": GID}
    assert tok.invalidacoes == 1 and len(http.chamadas) == 2
    gr, http = _graph([(401, {}), (401, {})], token=TokenFalso())
    with pytest.raises(ErroGraphNess, match="contato: HTTP 401"):
        gr.contato_criar(CONTA, "Ana", "1")
    assert len(http.chamadas) == 2


@pytest.mark.parametrize("nome,tel", [("", "1"), ("Ana", ""), ("  ", "1"), ("Ana", "  "), (None, "1"), ("Ana", 5),
                                      ("a" * 201, "1"), ("Ana", "1" * 31)])
def test_nome_ou_telefone_invalido_recusado(nome, tel):
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="contato inválido"):
        gr.contato_criar(CONTA, nome, tel)
    with pytest.raises(ErroGraphNess, match="contato inválido"):
        gr.contato_corrigir(CONTA, GID, ANTES, {"nome": nome, "telefone": tel})
    assert http.chamadas == []


def test_trava_no_modulo():
    mod = Path(gc.__file__).read_text()
    assert "DELETE" not in mod and "PUT" not in mod
    assert "PATCH" not in Path(g.__file__).read_text()
    assert not hasattr(GraphNess, "contato_apagar")
