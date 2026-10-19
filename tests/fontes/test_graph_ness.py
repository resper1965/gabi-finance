from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from gabi.fontes import graph_ness as g
from gabi.fontes.graph_ness import ErroGraphNess, GraphNess, TokenApp

SEGREDO = "SEGREDO-1"


def _http(respostas, chamadas=None):
    """respostas: fila de (status, corpo) ou Exception; guarda (metodo, url, corpo, cabecalhos)."""
    fila = list(respostas)
    chamadas = chamadas if chamadas is not None else []

    def http(metodo, url, corpo=None, cab=None):
        chamadas.append((metodo, url, corpo, cab))
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    http.chamadas = chamadas
    return http


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TokenFalso:
    def __init__(self):
        self.invalidacoes = 0
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"TOK{self.n}"

    def invalidar(self):
        self.invalidacoes += 1


def _graph(respostas, contas=("resper@ness.com.br",), token=None):
    http = _http(respostas)
    return GraphNess(token or TokenFalso(), list(contas), http=http), http


def test_token_troca_credenciais_e_cacheia():
    rel = Relogio()
    http = _http([(200, {"access_token": "A1", "expires_in": 3600}), (200, {"access_token": "A2", "expires_in": 3600})])
    t = TokenApp("ten-1", "cli-1", SEGREDO, http=http, agora=rel)
    assert t() == "A1" and t() == "A1"
    assert len(http.chamadas) == 1
    metodo, url, corpo, _ = http.chamadas[0]
    assert metodo == "POST" and url == "https://login.microsoftonline.com/ten-1/oauth2/v2.0/token"
    q = parse_qs(corpo.decode())
    assert q["grant_type"] == ["client_credentials"] and q["scope"] == ["https://graph.microsoft.com/.default"]
    assert q["client_id"] == ["cli-1"] and q["client_secret"] == [SEGREDO]
    rel.t += 3600 - 301
    assert t() == "A1"  # ainda dentro da folga de 300 s
    rel.t += 3
    assert t() == "A2"


def test_token_invalidar_forca_nova_troca():
    http = _http([(200, {"access_token": "A1", "expires_in": 3600}), (200, {"access_token": "A2", "expires_in": 3600})])
    t = TokenApp("t", "c", SEGREDO, http=http, agora=Relogio())
    assert t() == "A1"
    t.invalidar()
    assert t() == "A2"


def test_token_erro_nao_vaza_segredo():
    http = _http([(401, {"error_description": f"bad secret {SEGREDO}"})])
    with pytest.raises(ErroGraphNess) as e:
        TokenApp("t", "c", SEGREDO, http=http, agora=Relogio())()
    assert SEGREDO not in str(e.value) and "bad secret" not in str(e.value) and "-> 401" in str(e.value)


def test_token_resposta_invalida():
    for resp in ((200, {}), (200, {"access_token": "x"}), (200, [])):
        with pytest.raises(ErroGraphNess, match="resposta inválida"):
            TokenApp("t", "c", SEGREDO, http=_http([resp]), agora=Relogio())()


def test_repr_nao_mostra_segredo():
    t = TokenApp("t", "c", SEGREDO, http=_http([]), agora=Relogio())
    assert SEGREDO not in repr(t) and SEGREDO not in repr(GraphNess(t, ["a@x.com"]))


def test_get_repete_uma_vez_apos_401():
    tok = TokenFalso()
    gr, http = _graph([(401, {}), (200, {"value": []})], token=tok)
    assert gr._get(g.BASE + "/users/x/y") == {"value": []}
    assert tok.invalidacoes == 1 and [c[3]["Authorization"] for c in http.chamadas] == ["Bearer TOK1", "Bearer TOK2"]
    gr, _ = _graph([(401, {}), (401, {})])
    with pytest.raises(ErroGraphNess, match="-> 401"):
        gr._get(g.BASE + "/users/x/y")


def test_get_recusa_outro_host():
    gr, http = _graph([])
    for url in ("https://evil.example/x", "http://graph.microsoft.com/v1.0/x", "https://graph.microsoft.com.evil.example/v1.0/x"):
        with pytest.raises(ErroGraphNess, match="link inválido"):
            gr._get(url)
    assert http.chamadas == []


def test_get_erro_formato():
    gr, _ = _graph([(500, {"error": {"message": "texto do evento"}})])
    with pytest.raises(ErroGraphNess) as e:
        gr._get(g.BASE + "/users/x/y?$select=subject")
    assert str(e.value) == "GET /v1.0/users/x/y -> 500"
    gr, _ = _graph([(200, [])])
    with pytest.raises(ErroGraphNess, match="resposta inválida do Graph"):
        gr._get(g.BASE + "/users/x/y")
    gr, _ = _graph([ConnectionError("segredo na mensagem")])
    with pytest.raises(ErroGraphNess) as e:
        gr._get(g.BASE + "/users/x/y")
    assert str(e.value) == "Graph indisponível: ConnectionError"


def test_get_manda_cabecalhos_extras():
    gr, http = _graph([(200, {})])
    gr._get(g.BASE + "/users/x/y", {"Prefer": 'outlook.timezone="UTC"'})
    assert http.chamadas[0][3]["Prefer"] == 'outlook.timezone="UTC"' and http.chamadas[0][0] == "GET"


def test_conta_fora_da_lista_e_recusada():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr._conta("outro@ness.com.br")
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr._conta(None)
    assert gr._conta("RESPER@ness.com.br") == "resper@ness.com.br" and http.chamadas == []


def test_do_ambiente():
    env = {"M365_TENANT_ID": "t", "M365_CLIENT_ID": "c", "M365_CLIENT_SECRET": SEGREDO}
    assert g.graph_ness_do_ambiente({}) is None
    for falta in env:
        assert g.graph_ness_do_ambiente({k: v for k, v in env.items() if k != falta}) is None
    assert g.graph_ness_do_ambiente(env).contas() == ["resper@ness.com.br"]
    assert g.graph_ness_do_ambiente({**env, "M365_CONTAS": "a@x.com, B@x.com"}).contas() == ["a@x.com", "b@x.com"]


def test_so_leitura_no_codigo():
    texto = Path(g.__file__).read_text()
    for proibido in ("PATCH", "PUT", "DELETE"):
        assert proibido not in texto
    assert texto.count('"POST"') == 1
