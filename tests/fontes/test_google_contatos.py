import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest

from gabi.fontes import google_contatos as gc
from gabi.fontes.google_contatos import (ESCOPO, ErroGoogleContatos, GoogleContatos, TokenOAuth, listar_contatos,
                                          google_contatos_do_ambiente)
from gabi.fontes.ponte import ERROS, PERMITIDOS, Ponte, PonteContatos, Servidor

SEGREDO = "refresh-SEGREDO-123"
CLIENT_SEC = "client-SEGREDO-456"


def _pagina(nomes, proximo=None):
    r = {"connections": [{"names": [{"displayName": n}], "phoneNumbers": [{"value": t}]} for n, t in nomes]}
    if proximo:
        r["nextPageToken"] = proximo
    return r


def test_listar_pagina_e_so_pede_nome_telefone_e_email():
    chamadas = []
    paginas = {None: _pagina([("Ana", "(11) 91234-5678")], "p2"), "p2": _pagina([("Bia", "11 98888-7777")])}

    def http(m, url, corpo=None, cab=None):
        chamadas.append((m, url, cab))
        u = urlparse(url)
        q = parse_qs(u.query)
        assert u.path == "/v1/people/me/connections"
        assert q["personFields"] == ["names,phoneNumbers,emailAddresses"] and q["sources"] == ["READ_SOURCE_TYPE_CONTACT"]
        return 200, paginas[q.get("pageToken", [None])[0]]

    r = listar_contatos("a@gmail.com", lambda c: "TOK", http=http)
    assert r == [{"nome": "Ana", "telefone": "(11) 91234-5678"}, {"nome": "Bia", "telefone": "11 98888-7777"}]
    assert len(chamadas) == 2 and all(c[2]["Authorization"] == "Bearer TOK" for c in chamadas)
    assert "photos" not in chamadas[0][1] and "addresses" not in chamadas[0][1].replace("emailAddresses", "") and "biographies" not in chamadas[0][1]
    assert ESCOPO == "https://www.googleapis.com/auth/contacts.readonly"


def test_contato_com_varios_telefones_e_sem_nome_ou_sem_telefone():
    corpo = {"connections": [
        {"names": [{"displayName": "Ana"}], "phoneNumbers": [{"value": "1"}, {"value": "2"}], "emailAddresses": [{"value": " X@Y.com "}]},
        {"phoneNumbers": [{"value": "3"}]}, {"names": [{"displayName": "Sem"}]}]}
    r = listar_contatos("a@gmail.com", lambda c: "T", http=lambda *a, **k: (200, corpo))
    assert r == [{"nome": "Ana", "telefone": "1", "emails": ["x@y.com"]}, {"nome": "Ana", "telefone": "2", "emails": ["x@y.com"]}, {"nome": None, "telefone": "3"}]
    assert all(set(x) <= {"nome", "telefone", "emails"} for x in r)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_erro_http_e_tipado_e_nao_ecoa_corpo_nem_segredo(status):
    http = lambda *a, **k: (status, {"error": {"message": f"token {SEGREDO} inválido"}})
    with pytest.raises(ErroGoogleContatos) as e:
        listar_contatos("a@gmail.com", lambda c: SEGREDO, http=http)
    assert SEGREDO not in str(e.value) and str(status) in str(e.value)


def test_falha_de_rede_e_tipada_sem_segredo():
    def http(*a, **k):
        raise ConnectionError(f"x {SEGREDO}")
    with pytest.raises(ErroGoogleContatos) as e:
        listar_contatos("a@gmail.com", lambda c: SEGREDO, http=http)
    assert SEGREDO not in str(e.value) and e.value.__cause__ is None and e.value.__context__ is None


def test_paginacao_infinita_e_cortada():
    http = lambda *a, **k: (200, _pagina([("A", "1")], "mesmo"))
    with pytest.raises(ErroGoogleContatos):
        listar_contatos("a@gmail.com", lambda c: "T", http=http)


def test_resposta_que_nao_e_objeto_e_erro():
    with pytest.raises(ErroGoogleContatos):
        listar_contatos("a@gmail.com", lambda c: "T", http=lambda *a, **k: (200, [1]))


def _token(refresh=None, expira=3600, relogio=None):
    chamadas = []

    def http(m, url, corpo=None, cab=None):
        chamadas.append((m, url, corpo, cab))
        return 200, {"access_token": f"acc{len(chamadas)}", "expires_in": expira}
    t = TokenOAuth("cid", CLIENT_SEC, {"GOOGLE_REFRESH_RESPER_GMAIL_COM": SEGREDO} if refresh is None else refresh, http=http,
                   relogio=relogio or (lambda: 1000.0))
    return t, chamadas


def test_token_oauth_troca_refresh_por_access_e_nao_loga_segredo():
    t, ch = _token()
    assert t("resper@gmail.com") == "acc1"
    m, url, corpo, cab = ch[0]
    assert m == "POST" and url == "https://oauth2.googleapis.com/token"
    q = parse_qs(corpo.decode() if isinstance(corpo, bytes) else corpo)
    assert q == {"grant_type": ["refresh_token"], "client_id": ["cid"], "client_secret": [CLIENT_SEC], "refresh_token": [SEGREDO]}
    assert cab["Content-Type"] == "application/x-www-form-urlencoded"
    assert SEGREDO not in repr(t) and CLIENT_SEC not in repr(t) and SEGREDO not in str(vars(t).get("_http", ""))


def test_token_400_diz_token_recusado_e_sem_refresh_continua_nao_autorizada():
    t = TokenOAuth("cid", "s", {"GOOGLE_REFRESH_A_B_COM": "r"}, http=lambda *a, **k: (400, {}))
    with pytest.raises(ErroGoogleContatos) as e:
        t("a@b.com")
    assert str(e.value) == "token recusado: a@b.com"
    with pytest.raises(ErroGoogleContatos) as e:
        t("outra@b.com")
    assert str(e.value) == "conta não autorizada: outra@b.com"


def test_cache_do_token_usa_relogio_monotonico(monkeypatch):
    agora = [50.0]
    monkeypatch.setattr(time, "monotonic", lambda: agora[0])
    n = []
    t = TokenOAuth("c", "s", {"GOOGLE_REFRESH_A_B_COM": "r"}, http=lambda *a, **k: (n.append(1) or (200, {"access_token": f"a{len(n)}", "expires_in": 3600})))
    t("a@b.com"); t("a@b.com")
    assert len(n) == 1
    agora[0] += 3600
    assert t("a@b.com") == "a2"


def test_401_do_people_api_invalida_o_token_e_tenta_uma_vez_com_token_novo():
    emitidos = []

    def http_tok(m, url, corpo=None, cab=None):
        emitidos.append(1)
        return 200, {"access_token": f"acc{len(emitidos)}", "expires_in": 3600}
    t = TokenOAuth("c", "s", {"GOOGLE_REFRESH_A_B_COM": "r"}, http=http_tok)
    vistos = []

    def http(m, url, corpo=None, cab=None):
        vistos.append(cab["Authorization"])
        return (401, {}) if len(vistos) == 1 else (200, _pagina([("A", "1")]))
    assert listar_contatos("a@b.com", t, http=http) == [{"nome": "A", "telefone": "1"}]
    assert vistos == ["Bearer acc1", "Bearer acc2"]
    sempre401 = []
    with pytest.raises(ErroGoogleContatos) as e:
        listar_contatos("a@b.com", t, http=lambda m, u, c=None, h=None: (sempre401.append(1) or (401, {})))
    assert len(sempre401) == 2 and "401" in str(e.value)


def test_nome_e_telefone_primarios_e_canonical_form():
    corpo = {"connections": [{
        "names": [{"displayName": "Outro"}, {"displayName": "Principal", "metadata": {"primary": True}}],
        "phoneNumbers": [{"value": "(11) 1111-1111"}, {"value": "+1 (415) 555-2671", "canonicalForm": "+14155552671", "metadata": {"primary": True}}]}]}
    r = listar_contatos("a@b.com", lambda c: "T", http=lambda *a, **k: (200, corpo))
    assert r == [{"nome": "Principal", "telefone": "+1 (415) 555-2671", "canonico": "+14155552671"},
                 {"nome": "Principal", "telefone": "(11) 1111-1111"}]  # o primário vem primeiro; todos os telefones seguem listados


class _Resp:
    def __init__(self, status=200, corpo=b"{}"):
        self.status, self._corpo = status, corpo

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_real_falha_de_rede_levanta_fora_do_except_sem_contexto_e_sem_segredo(monkeypatch):
    def urlopen(req, timeout=None):
        raise urllib.error.URLError(f"falhou com {SEGREDO}")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(ErroGoogleContatos) as e:
        gc._http_real("GET", "https://x/", None, {"Authorization": f"Bearer {SEGREDO}"})
    assert e.value.__context__ is None and e.value.__cause__ is None and SEGREDO not in str(e.value)


def test_http_real_json_invalido_tambem_sem_contexto(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(200, b"nao e json " + SEGREDO.encode()))
    with pytest.raises(ErroGoogleContatos) as e:
        gc._http_real("GET", "https://x/")
    assert e.value.__context__ is None and SEGREDO not in str(e.value)


def test_http_real_http_error_fecha_sem_ler_o_corpo(monkeypatch):
    estado = {"lido": False, "fechado": False}

    class Erro(urllib.error.HTTPError):
        def read(self, *a):
            estado["lido"] = True
            return SEGREDO.encode()

        def close(self):
            estado["fechado"] = True

    def urlopen(req, timeout=None):
        raise Erro("https://x/", 403, "proibido", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert gc._http_real("GET", "https://x/") == (403, {})
    assert estado == {"lido": False, "fechado": True}


def test_token_fica_em_cache_ate_60s_antes_de_expirar():
    agora = [1000.0]
    t, ch = _token(expira=3600, relogio=lambda: agora[0])
    t("resper@gmail.com"); t("resper@gmail.com")
    assert len(ch) == 1
    agora[0] = 1000 + 3600 - 61
    t("resper@gmail.com")
    assert len(ch) == 1
    agora[0] = 1000 + 3600 - 59
    assert t("resper@gmail.com") == "acc2" and len(ch) == 2


def test_conta_sem_refresh_token_e_erro_tipado_que_so_cita_a_conta():
    t, ch = _token()
    with pytest.raises(ErroGoogleContatos) as e:
        t("resper@ness.com.br")
    assert str(e.value) == "conta não autorizada: resper@ness.com.br" and ch == []


@pytest.mark.parametrize("status", [400, 401, 500])
def test_erro_na_troca_nao_vaza_corpo(status):
    t = TokenOAuth("cid", CLIENT_SEC, {"GOOGLE_REFRESH_A_B_COM": SEGREDO},
                   http=lambda *a, **k: (status, {"error_description": f"{SEGREDO} {CLIENT_SEC}"}))
    with pytest.raises(ErroGoogleContatos) as e:
        t("a@b.com")
    assert SEGREDO not in str(e.value) and CLIENT_SEC not in str(e.value)


def test_resposta_de_token_invalida():
    t = TokenOAuth("cid", "s", {"GOOGLE_REFRESH_A_B_COM": "r"}, http=lambda *a, **k: (200, {"expires_in": 5}))
    with pytest.raises(ErroGoogleContatos):
        t("a@b.com")


def test_conta_com_formato_estranho_e_recusada():
    t, _ = _token()
    with pytest.raises(ErroGoogleContatos):
        t("x\nGOOGLE_REFRESH")


def test_do_ambiente_none_sem_cliente_e_objeto_com_cliente():
    assert google_contatos_do_ambiente({}) is None
    assert google_contatos_do_ambiente({"GOOGLE_CLIENT_ID": "a"}) is None
    g = google_contatos_do_ambiente({"GOOGLE_CLIENT_ID": "a", "GOOGLE_CLIENT_SECRET": "b"})
    assert isinstance(g, GoogleContatos) and "b" not in repr(g)


# ---- ponte ----
class _Falso:
    def listar(self, conta):
        if conta == "ruim@x.com":
            raise ErroGoogleContatos("conta não autorizada: ruim@x.com")
        if conta == "boom@x.com":
            raise RuntimeError(SEGREDO)
        return [{"nome": "Ana", "telefone": "1"}]

    def segredo(self):
        return SEGREDO


@pytest.fixture
def sock(tmp_path):
    srv = Servidor(tmp_path / "f.sock", {"google_contatos": _Falso(), "paperless": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path / "f.sock"
    srv.shutdown(); srv.server_close()


def test_ponte_lista_branca_e_erro_registrado():
    assert PERMITIDOS["google_contatos"] == frozenset({"listar"})
    assert ERROS["google_contatos"] is ErroGoogleContatos


def test_ponte_listar_cruza_e_metodo_fora_da_lista_e_proibido(sock):
    assert PonteContatos(sock).listar("a@x.com") == [{"nome": "Ana", "telefone": "1"}]
    with pytest.raises(ErroGoogleContatos):
        Ponte(sock, "google_contatos")._chamar("segredo")


def test_ponte_erro_tipado_cruza_e_interno_nao_vaza(sock):
    with pytest.raises(ErroGoogleContatos) as e:
        PonteContatos(sock).listar("ruim@x.com")
    assert str(e.value) == "conta não autorizada: ruim@x.com"
    with pytest.raises(ErroGoogleContatos) as e:
        PonteContatos(sock).listar("boom@x.com")
    assert SEGREDO not in str(e.value)


def test_ponte_nao_configurada(tmp_path):
    srv = Servidor(tmp_path / "n.sock", {"google_contatos": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = PonteContatos(tmp_path / "n.sock")
        assert p.configurada() is False
        with pytest.raises(ErroGoogleContatos):
            p.listar("a@x.com")
    finally:
        srv.shutdown(); srv.server_close()


def test_ponte_indisponivel_e_erro_tipado(tmp_path):
    with pytest.raises(ErroGoogleContatos):
        PonteContatos(tmp_path / "nada.sock").listar("a@x.com")


def test_emails_do_contato_primario_primeiro_normalizados_sem_repetir_e_contato_so_com_email():
    corpo = {"connections": [
        {"names": [{"displayName": "Ana"}], "phoneNumbers": [{"value": "1"}],
         "emailAddresses": [{"value": "casa@x.com"}, {"value": "Trab@Y.com", "metadata": {"primary": True}}, {"value": "trab@y.com"}, {"value": "lixo"}, {"value": 5}, {"value": "a b@x.com"}]},
        {"names": [{"displayName": "Só Email"}], "emailAddresses": [{"value": "so@x.com"}]},
        {"names": [{"displayName": "Nada"}], "emailAddresses": [{"value": "invalido"}]}]}
    r = listar_contatos("a@gmail.com", lambda c: "T", http=lambda *a, **k: (200, corpo))
    assert r == [{"nome": "Ana", "telefone": "1", "emails": ["trab@y.com", "casa@x.com"]}, {"nome": "Só Email", "telefone": None, "emails": ["so@x.com"]}]
