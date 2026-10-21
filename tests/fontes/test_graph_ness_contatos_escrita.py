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
    assert "PUT" not in mod and mod.count('"DELETE"') == 1  # o único DELETE é o de apagar contato inteiro (ADR-021)
    assert "PATCH" not in Path(g.__file__).read_text()
    assert not hasattr(GraphNess, "contato_apagar_tudo")


# ---------------- limpeza (ADR-021): renomear, apagar telefone, apagar contato ----------------
URL_ID = f"{URL}/AAMkAGI2TG93AAA%3D"


def test_renomear_so_displayname_apos_reler():
    gr, http = _graph([(200, {"displayName": "Ana⁹"}), (200, {})])
    assert gr.contato_renomear(CONTA, GID, "Ana⁹", "Ana") == {"resultado": "ok"}
    leitura, escrita = http.chamadas
    assert leitura[0] == "GET" and leitura[1] == f"{URL_ID}?$select=displayName"
    assert escrita[0] == "PATCH" and escrita[1] == URL_ID and json.loads(escrita[2]) == {"displayName": "Ana"}


def test_renomear_alterado_nao_escreve():
    gr, http = _graph([(200, {"displayName": "Outro"})])
    assert gr.contato_renomear(CONTA, GID, "Ana⁹", "Ana") == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


def test_apagar_telefone_mobile_manda_null():
    gr, http = _graph([(200, {"mobilePhone": "123", "homePhones": [], "businessPhones": []}), (200, {})])
    assert gr.contato_apagar_telefone(CONTA, GID, "mobile", "123") == {"resultado": "ok"}
    leitura, escrita = http.chamadas
    assert leitura[1] == f"{URL_ID}?$select=mobilePhone,homePhones,businessPhones"
    assert escrita[0] == "PATCH" and json.loads(escrita[2]) == {"mobilePhone": None}


def test_apagar_telefone_home_preserva_o_outro():
    gr, http = _graph([(200, {"mobilePhone": None, "homePhones": ["111", "222"], "businessPhones": []}), (200, {})])
    assert gr.contato_apagar_telefone(CONTA, GID, "home", "111") == {"resultado": "ok"}
    assert json.loads(http.chamadas[1][2]) == {"homePhones": ["222"]}


@pytest.mark.parametrize("campo,relida", [("mobile", {"mobilePhone": "999", "homePhones": [], "businessPhones": []}),
                                          ("home", {"mobilePhone": None, "homePhones": ["222"], "businessPhones": []}),
                                          ("business", {"mobilePhone": None, "homePhones": [], "businessPhones": []})])
def test_apagar_telefone_alterado_nao_escreve(campo, relida):
    gr, http = _graph([(200, relida)])
    assert gr.contato_apagar_telefone(CONTA, GID, campo, "111") == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


def test_apagar_telefone_campo_invalido_sem_http():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="contato inválido"):
        gr.contato_apagar_telefone(CONTA, GID, "fax", "111")
    assert http.chamadas == []


def test_apagar_contato_faz_delete_apos_conferir():
    gr, http = _graph([(200, {"displayName": "U", "mobilePhone": "123", "homePhones": [], "businessPhones": [], "emailAddresses": []}), (204, None)])
    assert gr.contato_apagar(CONTA, GID, "U", "123") == {"resultado": "ok"}
    leitura, escrita = http.chamadas
    assert leitura[1] == f"{URL_ID}?$select=displayName,mobilePhone,homePhones,businessPhones,emailAddresses,personalNotes,companyName,jobTitle,department,birthday"
    assert escrita[0] == "DELETE" and escrita[1] == URL_ID and escrita[2] is None


@pytest.mark.parametrize("relida", [
    {"displayName": "Outro", "mobilePhone": "1", "homePhones": [], "businessPhones": [], "emailAddresses": []},
    {"displayName": "U", "mobilePhone": "1", "homePhones": [], "businessPhones": [], "emailAddresses": [{"address": "a@b.com"}]},
    {"displayName": "U", "mobilePhone": "1", "homePhones": ["2"], "businessPhones": [], "emailAddresses": []},
    {"displayName": "U", "mobilePhone": "999", "homePhones": [], "businessPhones": [], "emailAddresses": []},   # trocou o número depois da proposta
    {"displayName": "U", "mobilePhone": None, "homePhones": [], "businessPhones": [], "emailAddresses": []},   # ficou sem telefone
])
def test_apagar_contato_recusa_o_que_mudou(relida):
    gr, http = _graph([(200, relida)])
    assert gr.contato_apagar(CONTA, GID, "U", "1") == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


def test_limpeza_erro_nao_vaza_nome_nem_telefone():
    gr, _ = _graph([(200, {"displayName": "U", "mobilePhone": "999", "homePhones": [], "businessPhones": [], "emailAddresses": []}), (500, {"x": "U 999"})])
    with pytest.raises(ErroGraphNess) as e:
        gr.contato_apagar(CONTA, GID, "U", "999")
    assert str(e.value) == "contato: HTTP 500"


def test_limpeza_recusa_conta_e_id_invalidos_sem_http():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.contato_apagar("x@y.com", GID, "U", "1")
    with pytest.raises(ErroGraphNess, match="id de contato inválido"):
        gr.contato_renomear(CONTA, "../x", "A", "B")
    assert http.chamadas == []


# ---------------- enriquecer (ADR-022): adicionar e-mail ----------------
def _relida_email(**kw):
    base = {"displayName": "U", "mobilePhone": "(11) 9", "homePhones": [], "businessPhones": [], "emailAddresses": []}
    return {**base, **kw}


def test_adicionar_email_escreve_so_emailaddresses():
    gr, http = _graph([(200, _relida_email()), (200, {})])
    assert gr.contato_adicionar_email(CONTA, GID, "U", "(11) 9", ["a@x.com", "b@x.com"]) == {"resultado": "ok"}
    leitura, escrita = http.chamadas
    assert leitura[0] == "GET" and leitura[1] == f"{URL_ID}?$select=displayName,mobilePhone,homePhones,businessPhones,emailAddresses"
    assert escrita[0] == "PATCH" and escrita[1] == URL_ID
    assert json.loads(escrita[2]) == {"emailAddresses": [{"address": "a@x.com"}, {"address": "b@x.com"}]}


@pytest.mark.parametrize("relida", [
    _relida_email(displayName="Outro"),                       # nome mudou
    _relida_email(mobilePhone="(11) 8"),                      # telefone mudou
    _relida_email(homePhones=["2"]),                          # ganhou outro telefone
    _relida_email(mobilePhone=None),                          # ficou sem telefone
    _relida_email(emailAddresses=[{"address": "a@b.com"}]),   # já tem e-mail
])
def test_adicionar_email_alterado_nao_escreve(relida):
    gr, http = _graph([(200, relida)])
    assert gr.contato_adicionar_email(CONTA, GID, "U", "(11) 9", ["a@x.com"]) == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


@pytest.mark.parametrize("emails", [[], ["a@x.com"] * 6, ["semarroba"], ["a@" + "x" * 253], "a@x.com", [1]])
def test_adicionar_email_valida_entrada(emails):
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="contato inválido"):
        gr.contato_adicionar_email(CONTA, GID, "U", "(11) 9", emails)
    assert http.chamadas == []


def test_adicionar_email_id_invalido_sem_http():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="id de contato inválido"):
        gr.contato_adicionar_email(CONTA, "../x", "U", "1", ["a@x.com"])
    assert http.chamadas == []


def test_adicionar_email_nunca_usa_delete():
    gr, http = _graph([(200, _relida_email()), (200, {})])
    gr.contato_adicionar_email(CONTA, GID, "U", "(11) 9", ["a@x.com"])
    assert "DELETE" not in [c[0] for c in http.chamadas]


def test_adicionar_email_erro_nao_vaza_dados():
    gr, _ = _graph([(200, _relida_email()), (500, {"x": "U a@x.com"})])
    with pytest.raises(ErroGraphNess) as e:
        gr.contato_adicionar_email(CONTA, GID, "U", "(11) 9", ["a@x.com"])
    assert str(e.value) == "contato: HTTP 500"


@pytest.mark.parametrize("extra", [{"personalNotes": "mãe da Sirlene"}, {"companyName": "ACME"}, {"jobTitle": "Dentista"}])
def test_apagar_contato_recusa_o_que_tem_notas_ou_empresa(extra):
    relida = {"displayName": "U", "mobilePhone": "1", "homePhones": [], "businessPhones": [], "emailAddresses": [], **extra}
    gr, http = _graph([(200, relida)])
    assert gr.contato_apagar(CONTA, GID, "U", "1") == {"resultado": "alterado"}
    assert [c[0] for c in http.chamadas] == ["GET"]


def test_apagar_contato_ignora_espaco_nas_pontas_do_nome():
    gr, http = _graph([(200, {"displayName": " U ", "mobilePhone": "1", "homePhones": [], "businessPhones": [], "emailAddresses": []}), (204, None)])
    assert gr.contato_apagar(CONTA, GID, "U", "1") == {"resultado": "ok"}
