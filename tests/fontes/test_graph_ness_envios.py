import json
import re
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from gabi.fontes import graph_ness as g
from gabi.fontes import graph_ness_envios as ge
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.fontes.graph_ness_envios import TokenDelegado
from tests.fontes.test_graph_ness import Relogio, TokenFalso, _graph, _http

CONTA = "resper@ness.com.br"
CHAVE = "0123456789abcdefghijklmnop"
REFRESH = "REFRESH-SEGREDO-1"
ESCOPO = ("https://graph.microsoft.com/ChatMessage.Send https://graph.microsoft.com/ChannelMessage.Send "
          "https://graph.microsoft.com/Team.ReadBasic.All https://graph.microsoft.com/Channel.ReadBasic.All offline_access")


class DelegadoFalso(TokenFalso):
    conta = CONTA

    def __call__(self):
        self.n += 1
        return f"DEL{self.n}"


def _evento(**kw):
    return {"conta": CONTA, "provedor": "graph", "titulo": "Reunião <b>X</b>", "inicio_utc": "2026-10-23T13:00:00Z",
            "fim_utc": "2026-10-23T14:00:00Z", "fuso": "America/Sao_Paulo", "convidados": ["ana@x.com", "bia@y.com"],
            "descricao": "pauta", "online": False, **kw}


# ---------------- evento ----------------
def test_evento_criar_url_e_corpo_exatos():
    gr, http = _graph([(201, {"id": "AAMkEVT="})], token_teams=DelegadoFalso())
    assert gr.evento_criar(CONTA, CHAVE, _evento()) == {"externo_id": "AAMkEVT="}
    metodo, url, corpo, cab = http.chamadas[0]
    assert metodo == "POST" and url == "https://graph.microsoft.com/v1.0/users/resper%40ness.com.br/events"
    assert cab["Authorization"] == "Bearer TOK1" and cab["Content-Type"] == "application/json"
    assert json.loads(corpo) == {
        "subject": "Reunião <b>X</b>", "body": {"contentType": "text", "content": "pauta"},
        "start": {"dateTime": "2026-10-23T13:00:00", "timeZone": "UTC"}, "end": {"dateTime": "2026-10-23T14:00:00", "timeZone": "UTC"},
        "attendees": [{"emailAddress": {"address": "ana@x.com"}, "type": "required"}, {"emailAddress": {"address": "bia@y.com"}, "type": "required"}],
        "transactionId": CHAVE}


def test_evento_online_pede_teams():
    gr, http = _graph([(201, {"id": "AAMkEVT="})])
    gr.evento_criar(CONTA, CHAVE, _evento(online=True))
    corpo = json.loads(http.chamadas[0][2])
    assert corpo["isOnlineMeeting"] is True and corpo["onlineMeetingProvider"] == "teamsForBusiness"


def test_evento_401_renova_token_uma_vez():
    tok = TokenFalso()
    gr, http = _graph([(401, {}), (201, {"id": "AAMkEVT="})], token=tok)
    assert gr.evento_criar(CONTA, CHAVE, _evento()) == {"externo_id": "AAMkEVT="}
    assert tok.invalidacoes == 1 and len(http.chamadas) == 2


def test_evento_erro_http_sem_conteudo():
    gr, _ = _graph([(400, {"error": {"message": "Reunião <b>X</b> ana@x.com"}})])
    with pytest.raises(ErroGraphNess) as e:
        gr.evento_criar(CONTA, CHAVE, _evento())
    assert str(e.value) == "evento_criar -> 400" and e.value.status == 400


def test_evento_resposta_sem_id():
    gr, _ = _graph([(201, {})])
    with pytest.raises(ErroGraphNess, match="resposta inválida do Graph"):
        gr.evento_criar(CONTA, CHAVE, _evento())


def test_evento_chave_invalida_nao_chama():
    gr, http = _graph([])
    for chave in ("", "CURTA", "x" * 26, None):
        with pytest.raises(ErroGraphNess, match="chave inválida"):
            gr.evento_criar(CONTA, chave, _evento())
    assert http.chamadas == []


# ---------------- conta ----------------
def test_conta_fora_da_lista():
    gr, http = _graph([], token_teams=DelegadoFalso())
    for chamar in (lambda: gr.evento_criar("outro@ness.com.br", CHAVE, _evento(conta="outro@ness.com.br")),
                   lambda: gr.teams_equipes("outro@ness.com.br"),
                   lambda: gr.teams_canais("outro@ness.com.br", "eq-1"),
                   lambda: gr.teams_chat_enviar("outro@ness.com.br", "19:a@thread.v2", "oi"),
                   lambda: gr.teams_canal_enviar("outro@ness.com.br", "eq-1", "19:c@thread.tacv2", "oi")):
        with pytest.raises(ErroGraphNess, match="^conta não autorizada$"):
            chamar()
    assert http.chamadas == []


def test_teams_conta_diferente_do_login():
    outro = DelegadoFalso()
    outro.conta = "outra@ness.com.br"
    gr, http = _graph([], contas=(CONTA, "outra@ness.com.br"), token_teams=outro)
    with pytest.raises(ErroGraphNess, match="^login_teams_conta_diferente$"):
        gr.teams_chat_enviar(CONTA, "19:a@thread.v2", "oi")
    assert http.chamadas == []


def test_sem_login_teams():
    gr, http = _graph([])
    for chamar in (lambda: gr.teams_equipes(CONTA), lambda: gr.teams_canais(CONTA, "eq-1"),
                   lambda: gr.teams_chat_enviar(CONTA, "19:a@thread.v2", "oi"),
                   lambda: gr.teams_canal_enviar(CONTA, "eq-1", "19:c@thread.tacv2", "oi")):
        with pytest.raises(ErroGraphNess, match="^teams_sem_login$"):
            chamar()
    assert http.chamadas == []


# ---------------- teams ----------------
def test_teams_equipes_e_canais():
    gr, http = _graph([(200, {"value": [{"id": "eq-1", "displayName": "Comercial"}, {"id": "x/y", "displayName": "ruim"}, "lixo"]}),
                       (200, {"value": [{"id": "19:c@thread.tacv2", "displayName": "Geral"}]})], token_teams=DelegadoFalso())
    assert gr.teams_equipes(CONTA) == [{"id": "eq-1", "nome": "Comercial"}]
    assert gr.teams_canais(CONTA, "eq-1") == [{"id": "19:c@thread.tacv2", "nome": "Geral"}]
    (m1, u1, c1, h1), (m2, u2, _, _) = http.chamadas
    assert m1 == m2 == "GET" and c1 is None and h1["Authorization"] == "Bearer DEL1"
    assert u1.startswith("https://graph.microsoft.com/v1.0/me/joinedTeams")
    assert u2.startswith("https://graph.microsoft.com/v1.0/teams/eq-1/channels")


def test_teams_canais_id_invalido():
    gr, http = _graph([], token_teams=DelegadoFalso())
    with pytest.raises(ErroGraphNess, match="equipe inválida"):
        gr.teams_canais(CONTA, "a/b")
    assert http.chamadas == []


def test_teams_chat_enviar_url_e_corpo():
    gr, http = _graph([(201, {"id": "1700000000000"})], token_teams=DelegadoFalso())
    assert gr.teams_chat_enviar(CONTA, "19:a@thread.v2", "oi") == {"externo_id": "1700000000000"}
    metodo, url, corpo, cab = http.chamadas[0]
    assert metodo == "POST" and url == "https://graph.microsoft.com/v1.0/chats/19%3Aa%40thread.v2/messages"
    assert json.loads(corpo) == {"body": {"contentType": "text", "content": "oi"}} and cab["Authorization"] == "Bearer DEL1"


def test_teams_canal_enviar_url_e_corpo():
    gr, http = _graph([(201, {"id": "1700000000001"})], token_teams=DelegadoFalso())
    assert gr.teams_canal_enviar(CONTA, "eq-1", "19:c@thread.tacv2", "oi") == {"externo_id": "1700000000001"}
    metodo, url, corpo, _ = http.chamadas[0]
    assert metodo == "POST" and url == "https://graph.microsoft.com/v1.0/teams/eq-1/channels/19%3Ac%40thread.tacv2/messages"
    assert json.loads(corpo) == {"body": {"contentType": "text", "content": "oi"}}


def test_teams_texto_com_html_vai_como_text():
    gr, http = _graph([(201, {"id": "1"}), (201, {"id": "2"})], token_teams=DelegadoFalso())
    gr.teams_chat_enviar(CONTA, "19:a@thread.v2", "<b>oi</b> & tchau")
    gr.teams_canal_enviar(CONTA, "eq-1", "19:c@thread.tacv2", "<b>oi</b> & tchau")
    for _, _, corpo, _ in http.chamadas:
        assert json.loads(corpo)["body"] == {"contentType": "text", "content": "<b>oi</b> & tchau"}


def test_teams_texto_fora_do_limite_nao_chama():
    gr, http = _graph([], token_teams=DelegadoFalso())
    for texto in ("", "x" * 4001, None):
        with pytest.raises(ErroGraphNess, match="texto inválido"):
            gr.teams_chat_enviar(CONTA, "19:a@thread.v2", texto)
    assert http.chamadas == []


def test_teams_401_renova_delegado_e_erro_sem_texto():
    tok = DelegadoFalso()
    gr, http = _graph([(401, {}), (403, {"error": {"message": "oi"}})], token_teams=tok)
    with pytest.raises(ErroGraphNess) as e:
        gr.teams_chat_enviar(CONTA, "19:a@thread.v2", "segredo do texto")
    assert str(e.value) == "teams_chat_enviar -> 403" and tok.invalidacoes == 1 and "segredo" not in str(e.value)


# ---------------- token delegado ----------------
def _delegado(respostas, rel=None):
    http = _http(respostas)
    return TokenDelegado("ten-1", "cli-1", REFRESH, CONTA, http=http, agora=rel or Relogio()), http


def test_token_delegado_troca_refresh_e_confere_me():
    rel = Relogio()
    t, http = _delegado([(200, {"access_token": "A1", "expires_in": 3600}), (200, {"userPrincipalName": "RESPER@ness.com.br"})], rel)
    assert t() == "A1" and t() == "A1"
    (m1, u1, c1, _), (m2, u2, _, h2) = http.chamadas
    assert m1 == "POST" and u1 == "https://login.microsoftonline.com/ten-1/oauth2/v2.0/token"
    q = parse_qs(c1.decode())
    assert q == {"grant_type": ["refresh_token"], "client_id": ["cli-1"], "refresh_token": [REFRESH], "scope": [ESCOPO]}
    assert m2 == "GET" and u2.startswith("https://graph.microsoft.com/v1.0/me") and h2["Authorization"] == "Bearer A1"
    assert t.conta == CONTA


def test_token_delegado_guarda_refresh_rotacionado_em_memoria():
    rel = Relogio()
    t, http = _delegado([(200, {"access_token": "A1", "expires_in": 3600, "refresh_token": "R2"}), (200, {"userPrincipalName": CONTA}),
                         (200, {"access_token": "A2", "expires_in": 3600})], rel)
    assert t() == "A1"
    t.invalidar()
    assert t() == "A2"
    assert parse_qs(http.chamadas[2][2].decode())["refresh_token"] == ["R2"]
    assert len(http.chamadas) == 3  # o /me só na primeira troca


def test_token_delegado_expirado():
    for status in (400, 401):
        t, _ = _delegado([(status, {"error_description": f"bad {REFRESH}"})])
        with pytest.raises(ErroGraphNess) as e:
            t()
        assert str(e.value) == "login_teams_expirado"


def test_token_delegado_outro_erro():
    t, _ = _delegado([(503, {})])
    with pytest.raises(ErroGraphNess) as e:
        t()
    assert str(e.value) == "troca de token teams -> 503"


def test_token_delegado_conta_diferente():
    t, http = _delegado([(200, {"access_token": "A1", "expires_in": 3600}), (200, {"userPrincipalName": "outra@ness.com.br"}),
                         (200, {"access_token": "A2", "expires_in": 3600}), (200, {"userPrincipalName": "outra@ness.com.br"})])
    for _ in range(2):  # continua recusando: o token nunca fica guardado
        with pytest.raises(ErroGraphNess) as e:
            t()
        assert str(e.value) == "login_teams_conta_diferente"
    assert "outra" not in str(e.value)


def test_token_delegado_resposta_invalida():
    for resp in ((200, {}), (200, {"access_token": "x"}), (200, [])):
        t, _ = _delegado([resp])
        with pytest.raises(ErroGraphNess, match="resposta inválida"):
            t()


def test_repr_oculto():
    t, _ = _delegado([])
    assert REFRESH not in repr(t) and repr(t) == "TokenDelegado(<oculto>)"
    gr, _ = _graph([], token_teams=t)
    assert REFRESH not in repr(gr)


def test_do_ambiente_monta_delegado_so_com_refresh():
    env = {"M365_TENANT_ID": "t", "M365_CLIENT_ID": "c", "M365_CLIENT_SECRET": "s", "M365_CONTAS": "A@x.com, b@x.com"}
    assert g.graph_ness_do_ambiente(env)._token_teams is None
    gr = g.graph_ness_do_ambiente({**env, "GRAPH_NESS_TEAMS_REFRESH": REFRESH})
    assert isinstance(gr._token_teams, TokenDelegado) and gr._token_teams.conta == "a@x.com"
    with pytest.raises(ErroGraphNess, match="teams_sem_login"):
        g.graph_ness_do_ambiente(env).teams_equipes("a@x.com")


# ---------------- trava no código ----------------
def test_envios_so_tem_os_verbos_e_urls_previstos():
    texto = Path(ge.__file__).read_text()
    verbos = set(re.findall(r'"([A-Z]{3,7})"', texto)) & {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "MERGE"}
    assert verbos == {"GET", "POST"}
    for proibido in ("/sendMail", "/reply", "/forward", "DELETE", "PATCH", '/chats"', "PUT"):
        assert proibido not in texto
    publicos = {n for n in vars(ge) if not n.startswith("_") and callable(getattr(ge, n)) and getattr(getattr(ge, n), "__module__", "") == ge.__name__}
    assert publicos == {"TokenDelegado", "evento_criar", "teams_equipes", "teams_canais", "teams_chat_enviar", "teams_canal_enviar"}
