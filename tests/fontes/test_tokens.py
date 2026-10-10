import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gabi.fontes.google import ErroGoogle, Google
from gabi.fontes.graph import ErroGraph, Graph
from gabi.fontes.tokens import cliente_do_ambiente, nome_da_variavel, token_google_oauth, token_graph


@pytest.fixture(scope="module")
def pem():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


class Http:
    def __init__(self, status=200, resp=None):
        self.status, self.resp, self.chamadas = status, resp or {"access_token": "T", "expires_in": 3600}, []

    def __call__(self, url, campos):
        self.chamadas.append((url, campos))
        return self.status, self.resp


def test_token_graph_usa_client_credentials_com_assertion_e_guarda_em_cache(pem):
    h, t = Http(), [1000.0]
    tok = token_graph("ten", "cid", pem, "x5", http=h, relogio=lambda: t[0])
    assert tok() == "T" and tok() == "T"
    assert len(h.chamadas) == 1
    url, campos = h.chamadas[0]
    assert url.endswith("/ten/oauth2/v2.0/token") and campos["grant_type"] == "client_credentials" and campos["client_assertion"].count(".") == 2
    t[0] += 3600  # venceu: pede outro
    tok()
    assert len(h.chamadas) == 2


def test_token_recusado_levanta_erro_com_status_para_pedir_reconexao():
    with pytest.raises(ErroGoogle, match="-> 400"):
        token_google_oauth("c", "s", "r", http=Http(400, {"error": "invalid_grant"}))()


def test_token_graph_recusado_levanta_erro_do_graph(pem):
    with pytest.raises(ErroGraph, match="-> 401"):
        token_graph("t", "c", pem, "x", http=Http(401, {"error": "invalid_client"}))()


def test_nome_da_variavel_do_refresh_token():
    assert nome_da_variavel("gabi@ness.com.br") == "GOOGLE_REFRESH_GABI_NESS_COM_BR"


def test_cliente_do_ambiente_escolhe_o_cliente_certo_e_devolve_none_sem_credencial(tmp_path, pem):
    chave = tmp_path / "k.pem"
    chave.write_bytes(pem)
    env = {"GRAPH_TENANT": "t", "GRAPH_CLIENT_ID": "c", "GRAPH_CERT_KEY_FILE": str(chave), "GRAPH_CERT_X5T": "x",
           "GOOGLE_SA_DOMINIOS": "bekaa.eu", "GOOGLE_SA_EMAIL": "sa@p.iam", "GOOGLE_SA_KEY_FILE": str(chave),
           "GOOGLE_OAUTH_CLIENT_ID": "i", "GOOGLE_OAUTH_CLIENT_SECRET": "s", "GOOGLE_REFRESH_RICARDO_NESS_COM_BR": "r"}
    c = cliente_do_ambiente(env, http=Http())
    assert isinstance(c({"provedor": "graph", "endereco": "a@ionic.health"}), Graph)
    assert isinstance(c({"provedor": "google", "endereco": "x@bekaa.eu"}), Google)
    assert isinstance(c({"provedor": "google", "endereco": "ricardo@ness.com.br"}), Google)
    assert c({"provedor": "google", "endereco": "outro@gmail.com"}) is None
    assert cliente_do_ambiente({})({"provedor": "graph", "endereco": "a@ionic.health"}) is None
