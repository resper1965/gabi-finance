import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from gabi.fontes import google_agenda as ga
from gabi.fontes.google_oauth import ErroGoogleOAuth

SEGREDO = "tok-SEGREDO-999"
JANELA = {"de": "2026-10-04T00:00:00+00:00", "ate": "2027-01-09T00:00:00+00:00"}


class Token:
    def __init__(self):
        self.invalidacoes = 0
        self.n = 0

    def __call__(self, conta):
        self.n += 1
        return f"TOK{self.n}"

    def invalidar(self, conta):
        self.invalidacoes += 1


def _http(respostas, chamadas):
    """respostas: lista de (status, corpo) consumida em ordem; guarda (url, query, cabeçalho)."""
    fila = list(respostas)

    def http(m, url, corpo=None, cab=None):
        assert m == "GET"
        chamadas.append((urlparse(url).path, parse_qs(urlparse(url).query), cab))
        return fila.pop(0)
    return http


def _ev(id_, resumo="Reunião", **extra):
    e = {"id": id_, "status": "confirmed", "summary": resumo, "etag": '"e1"', "updated": "2026-10-10T10:00:00.000Z",
         "start": {"dateTime": "2026-10-12T10:00:00-03:00"}, "end": {"dateTime": "2026-10-12T11:00:00-03:00"}}
    e.update(extra)
    return e


def test_listar_calendarios():
    ch = []
    corpo = {"items": [{"id": "resper@gmail.com", "summary": "Ricardo", "primary": True, "accessRole": "owner"},
                       {"id": "familia@group.calendar.google.com", "summary": "Família", "accessRole": "reader"}]}
    r = ga.listar_calendarios("resper@gmail.com", Token(), http=_http([(200, corpo)], ch))
    assert r == [{"id": "resper@gmail.com", "nome": "Ricardo", "principal": True},
                 {"id": "familia@group.calendar.google.com", "nome": "Família", "principal": False}]
    assert ch[0][0] == "/calendar/v3/users/me/calendarList"


def test_eventos_paginam_ate_o_fim_e_devolvem_o_sync_token_so_da_ultima_pagina():
    ch = []
    http = _http([(200, {"items": [_ev("a")], "nextPageToken": "p2"}), (200, {"items": [_ev("b")], "nextSyncToken": "SYNC1"})], ch)
    r = ga.listar_eventos("resper@gmail.com", "primary", None, JANELA, Token(), http=http)
    assert [e["externo_id"] for e in r.eventos] == ["a", "b"] and r.novo_sync_token == "SYNC1" and r.recarga_completa is False
    assert len(ch) == 2 and ch[1][1]["pageToken"] == ["p2"]


def test_carga_inicial_manda_janela_e_sync_token_nao_manda_janela():
    ch = []
    ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, {"items": [], "nextSyncToken": "S"})], ch))
    q = ch[0][1]
    assert q["singleEvents"] == ["true"] and q["timeMin"] == [JANELA["de"]] and q["timeMax"] == [JANELA["ate"]]
    ch2 = []
    ga.listar_eventos("a@gmail.com", "primary", "S", JANELA, Token(), http=_http([(200, {"items": [], "nextSyncToken": "S2"})], ch2))
    q2 = ch2[0][1]
    assert q2["syncToken"] == ["S"] and "timeMin" not in q2 and "timeMax" not in q2 and q2["singleEvents"] == ["true"]


def test_410_recarrega_a_janela_completa_sem_token():
    ch = []
    http = _http([(410, {}), (200, {"items": [_ev("a")], "nextSyncToken": "NOVO"})], ch)
    r = ga.listar_eventos("a@gmail.com", "primary", "VELHO", JANELA, Token(), http=http)
    assert r.recarga_completa is True and r.novo_sync_token == "NOVO" and [e["externo_id"] for e in r.eventos] == ["a"]
    assert "syncToken" in ch[0][1] and "syncToken" not in ch[1][1] and ch[1][1]["timeMin"] == [JANELA["de"]]


def test_410_sem_token_e_erro_tipado():
    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(410, {})], []))


def test_cancelado_vai_para_cancelados_e_nao_vira_evento():
    corpo = {"items": [_ev("a"), {"id": "b", "status": "cancelled"}, {"id": "c_20261012T130000Z", "status": "cancelled"}], "nextSyncToken": "S"}
    r = ga.listar_eventos("a@gmail.com", "primary", "S0", JANELA, Token(), http=_http([(200, corpo)], []))
    assert [e["externo_id"] for e in r.eventos] == ["a"] and r.cancelados == ["b", "c_20261012T130000Z"]


def test_visibilidade_private_e_confidential_marcam_privado():
    corpo = {"items": [_ev("a"), _ev("b", visibility="private"), _ev("c", visibility="confidential"), _ev("d", visibility="public"),
                       _ev("e", visibility="default")], "nextSyncToken": "S"}
    r = ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, corpo)], []))
    assert {e["externo_id"]: e["privado"] for e in r.eventos} == {"a": False, "b": True, "c": True, "d": False, "e": False}


def test_ical_uid_e_transparencia_livre_vem_do_google():
    corpo = {"items": [_ev("a", iCalUID="uid-a@google.com"), _ev("b", transparency="transparent"), _ev("c", transparency="opaque")], "nextSyncToken": "S"}
    r = ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, corpo)], []))
    por_id = {e["externo_id"]: e for e in r.eventos}
    assert por_id["a"]["ical_uid"] == "uid-a@google.com" and por_id["b"]["ical_uid"] is None
    assert {k: v["livre"] for k, v in por_id.items()} == {"a": False, "b": True, "c": False}


def test_nao_extrai_email_nem_local_so_a_contagem_de_participantes():
    corpo = {"items": [_ev("a", attendees=[{"email": "x@y.com"}, {"email": "z@w.com"}], location="Rua Secreta 1, São Paulo",
                           hangoutLink="https://meet.google.com/abc", organizer={"email": "o@x.com"})], "nextSyncToken": "S"}
    (e,) = ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, corpo)], [])).eventos
    assert e["participantes_qtd"] == 2 and e["link_reuniao"] == "https://meet.google.com/abc"
    assert e == {"externo_id": "a", "inicio": {"dateTime": "2026-10-12T10:00:00-03:00"}, "fim": {"dateTime": "2026-10-12T11:00:00-03:00"},
                 "titulo": "Reunião", "link_reuniao": "https://meet.google.com/abc", "participantes_qtd": 2, "status": "confirmed",
                 "etag": '"e1"', "atualizado_origem": "2026-10-10T10:00:00.000Z", "privado": False,
                 "ical_uid": None, "livre": False}
    blob = repr(e)
    assert "x@y.com" not in blob and "Secreta" not in blob and "o@x.com" not in blob


def test_401_invalida_o_token_e_repete_uma_vez():
    t, ch = Token(), []
    http = _http([(401, {}), (200, {"items": [_ev("a")], "nextSyncToken": "S"})], ch)
    r = ga.listar_eventos("a@gmail.com", "primary", None, JANELA, t, http=http)
    assert t.invalidacoes == 1 and len(ch) == 2 and ch[0][2]["Authorization"] != ch[1][2]["Authorization"] and len(r.eventos) == 1


def test_401_duas_vezes_e_erro_tipado_sem_segredo():
    http = _http([(401, {"error": SEGREDO}), (401, {"error": SEGREDO})], [])
    with pytest.raises(ErroGoogleOAuth) as e:
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=http)
    assert SEGREDO not in str(e.value) and "401" in str(e.value)


@pytest.mark.parametrize("status", [400, 403, 404, 429, 500])
def test_erro_http_e_tipado_sem_corpo(status):
    with pytest.raises(ErroGoogleOAuth) as e:
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(status, {"error": SEGREDO})] * 3, []))  # 3: a leitura repete 429/5xx
    assert SEGREDO not in str(e.value) and str(status) in str(e.value)


def test_teto_de_paginas_e_pagina_repetida():
    cont = {"n": 0}

    def sempre_mais(m, url, corpo=None, cab=None):
        cont["n"] += 1
        return 200, {"items": [], "nextPageToken": f"p{cont['n']}"}
    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=sempre_mais)
    assert cont["n"] == ga.MAX_PAGINAS

    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=lambda *a, **k: (200, {"items": [], "nextPageToken": "igual"}))


def test_id_do_calendario_vai_codificado_no_caminho():
    ch = []
    cal = "familia@group.calendar.google.com"
    ga.listar_eventos("a@gmail.com", cal, None, JANELA, Token(), http=_http([(200, {"items": [], "nextSyncToken": "S"})], ch))
    assert ch[0][0] == "/calendar/v3/calendars/familia%40group.calendar.google.com/events"


def test_conta_e_calendario_invalidos():
    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("não é conta", "primary", None, JANELA, Token(), http=lambda *a, **k: (200, {}))
    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("a@gmail.com", "", None, JANELA, Token(), http=lambda *a, **k: (200, {}))
    with pytest.raises(ErroGoogleOAuth):
        ga.listar_eventos("a@gmail.com", "x/../y", None, JANELA, Token(), http=lambda *a, **k: (200, {}))


def test_cliente_so_cria_evento_e_nao_tem_outro_metodo_de_escrita():
    """ADR-024: a única escrita é o insert (POST); nada de PUT/PATCH/DELETE nem update/patch/delete/move."""
    fonte = Path(ga.__file__).read_text()
    assert not re.search(r"""["'](PUT|PATCH|DELETE)["']""", fonte)
    assert not re.search(r"events\.(update|patch|delete|move|import|quickAdd)", fonte, re.I)
    assert not [n for n in dir(ga.GoogleAgenda) if n.lstrip("_").startswith(("apagar", "atualizar", "mover", "responder"))]


def test_objeto_da_ponte_devolve_json_puro_e_sem_credencial_e_none():
    http = _http([(200, {"items": [_ev("a")], "nextSyncToken": "S"})], [])
    g = ga.GoogleAgenda(Token(), http=http)
    r = g.listar_eventos("a@gmail.com", "primary", None, JANELA)
    assert isinstance(r, dict) and set(r) == {"eventos", "cancelados", "novo_sync_token", "recarga_completa"}
    assert ga.google_agenda_do_ambiente({}) is None
    assert ga.google_agenda_do_ambiente({"GOOGLE_CLIENT_ID": "i", "GOOGLE_CLIENT_SECRET": "s"}) is not None
    assert "SEGREDO" not in repr(g) and "TOK" not in repr(g)


def test_recusado_pelo_proprio_dono_conta_como_cancelado_e_o_de_outro_participante_nao():
    ch = []
    eu = _ev("recusei", attendees=[{"email": "outro@x.com", "responseStatus": "accepted"}, {"email": "eu@x.com", "self": True, "responseStatus": "declined"}])
    outro = _ev("outro_recusou", attendees=[{"email": "outro@x.com", "responseStatus": "declined"}, {"email": "eu@x.com", "self": True, "responseStatus": "accepted"}])
    r = ga.listar_eventos("a@x.com", "primary", None, JANELA, Token(), http=_http([(200, {"items": [eu, outro], "nextSyncToken": "S"})], ch))
    assert r.cancelados == ["recusei"] and [e["externo_id"] for e in r.eventos] == ["outro_recusou"]


def test_local_de_trabalho_nao_e_compromisso_mas_fora_do_escritorio_e():
    ch = []
    itens = [_ev("casa", eventType="workingLocation"), _ev("ferias", eventType="outOfOffice"), _ev("normal", eventType="default")]
    r = ga.listar_eventos("a@x.com", "primary", None, JANELA, Token(), http=_http([(200, {"items": itens, "nextSyncToken": "S"})], ch))
    assert [e["externo_id"] for e in r.eventos] == ["ferias", "normal"] and r.cancelados == []


def _link(**extra):
    corpo = {"items": [_ev("a", **extra)], "nextSyncToken": "S"}
    return ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, corpo)], [])).eventos[0]["link_reuniao"]


def test_link_de_reuniao_vem_do_conference_data_de_qualquer_provedor_e_so_https():
    """Agenda M8: Zoom/Teams adicionados ao evento chegam em conferenceData.entryPoints (video); hangoutLink continua valendo."""
    zoom = {"entryPoints": [{"entryPointType": "phone", "uri": "tel:+5511999990000"}, {"entryPointType": "video", "uri": "https://us02web.zoom.us/j/123"}],
            "conferenceSolution": {"name": "Zoom Meeting"}}
    assert _link(conferenceData=zoom) == "https://us02web.zoom.us/j/123"
    assert _link(conferenceData=zoom, hangoutLink="https://meet.google.com/abc") == "https://meet.google.com/abc"  # o Meet nativo vence
    assert _link(conferenceData={"entryPoints": [{"entryPointType": "video", "uri": "https://teams.microsoft.com/l/meetup-join/x"}]}) == "https://teams.microsoft.com/l/meetup-join/x"
    # só telefone, esquema que não é https e lixo: sem link
    assert _link(conferenceData={"entryPoints": [{"entryPointType": "phone", "uri": "tel:+5511999990000"}]}) is None
    assert _link(conferenceData={"entryPoints": [{"entryPointType": "video", "uri": "javascript:alert(1)"}]}) is None
    assert _link(conferenceData={"entryPoints": [{"entryPointType": "video", "uri": "http://x.com/j/1"}]}) is None
    assert _link(conferenceData="lixo") is None and _link(conferenceData={"entryPoints": "x"}) is None
    assert _link(location="https://zoom.us/j/999") is None  # o local nunca é lido (privacidade)


# ---- criar evento (ADR-024) ----
CHAVE = "0123456789abcdefghijklmnop"
EVENTO = {"conta": "resper@gmail.com", "provedor": "google", "titulo": "Alinhamento", "inicio_utc": "2026-10-23T13:00:00Z",
          "fim_utc": "2026-10-23T14:00:00Z", "fuso": "America/Sao_Paulo", "convidados": ["ana@x.com", "bia@y.com"],
          "descricao": "Pauta do dia", "online": True}
URL_CRIAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all&conferenceDataVersion=1"


def _http_post(respostas, chamadas):
    fila = list(respostas)

    def http(m, url, corpo=None, cab=None):
        chamadas.append((m, url, corpo, cab))
        return fila.pop(0)
    return http


def test_evento_criar_post_com_id_sendupdates_e_meet():
    ch = []
    r = ga.GoogleAgenda(Token(), http=_http_post([(200, {"id": CHAVE})], ch)).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert r == {"externo_id": CHAVE, "ja_existia": False}
    assert len(ch) == 1
    m, url, corpo, cab = ch[0]
    assert m == "POST" and url == URL_CRIAR and cab["Authorization"] == "Bearer TOK1"
    assert corpo == {"id": CHAVE, "summary": "Alinhamento", "description": "Pauta do dia",
                     "start": {"dateTime": "2026-10-23T13:00:00Z", "timeZone": "America/Sao_Paulo"},
                     "end": {"dateTime": "2026-10-23T14:00:00Z", "timeZone": "America/Sao_Paulo"},
                     "attendees": [{"email": "ana@x.com"}, {"email": "bia@y.com"}],
                     "conferenceData": {"createRequest": {"requestId": CHAVE, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}


def test_evento_criar_sem_online_nao_pede_conferencia():
    ch = []
    ga.GoogleAgenda(Token(), http=_http_post([(200, {"id": CHAVE})], ch)).evento_criar("resper@gmail.com", CHAVE, {**EVENTO, "online": False})
    _, url, corpo, _ = ch[0]
    assert "conferenceDataVersion" not in url and "conferenceData" not in corpo and "sendUpdates=all" in url


def test_evento_criar_409_e_ja_existia():
    r = ga.GoogleAgenda(Token(), http=_http_post([(409, {})], [])).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert r == {"externo_id": CHAVE, "ja_existia": True}


def test_evento_criar_4xx_levanta_com_status():
    with pytest.raises(ErroGoogleOAuth) as e:
        ga.GoogleAgenda(Token(), http=_http_post([(403, {})], [])).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert str(e.value) == "calendar.events.insert -> 403"


@pytest.mark.parametrize("chave", ["", "abc", "ABCDEFGHIJ", "w" * 26, "a" * 1025, "abcde/../x", None, 5])
def test_evento_criar_chave_invalida(chave):
    ch = []
    with pytest.raises(ErroGoogleOAuth):
        ga.GoogleAgenda(Token(), http=_http_post([], ch)).evento_criar("resper@gmail.com", chave, EVENTO)
    assert ch == []


def test_evento_criar_401_renova_token_uma_vez():
    ch, tok = [], Token()
    r = ga.GoogleAgenda(tok, http=_http_post([(401, {}), (200, {"id": CHAVE})], ch)).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert r["ja_existia"] is False and tok.invalidacoes == 1 and len(ch) == 2
    assert ch[0][3]["Authorization"] == "Bearer TOK1" and ch[1][3]["Authorization"] == "Bearer TOK2"
    with pytest.raises(ErroGoogleOAuth) as e:
        ga.GoogleAgenda(Token(), http=_http_post([(401, {}), (401, {})], [])).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert str(e.value) == "calendar.events.insert -> 401"


def test_evento_criar_erro_nao_vaza_conteudo():
    with pytest.raises(ErroGoogleOAuth) as e:
        ga.GoogleAgenda(Token(), http=_http_post([(500, {"error": "Alinhamento ana@x.com"})], [])).evento_criar("resper@gmail.com", CHAVE, EVENTO)
    assert "Alinhamento" not in str(e.value) and "ana@x.com" not in str(e.value)
