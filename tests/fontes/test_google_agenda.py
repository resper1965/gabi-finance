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


def test_nao_extrai_email_nem_local_so_a_contagem_de_participantes():
    corpo = {"items": [_ev("a", attendees=[{"email": "x@y.com"}, {"email": "z@w.com"}], location="Rua Secreta 1, São Paulo",
                           hangoutLink="https://meet.google.com/abc", organizer={"email": "o@x.com"})], "nextSyncToken": "S"}
    (e,) = ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(200, corpo)], [])).eventos
    assert e["participantes_qtd"] == 2 and e["link_reuniao"] == "https://meet.google.com/abc"
    assert e == {"externo_id": "a", "inicio": {"dateTime": "2026-10-12T10:00:00-03:00"}, "fim": {"dateTime": "2026-10-12T11:00:00-03:00"},
                 "titulo": "Reunião", "link_reuniao": "https://meet.google.com/abc", "participantes_qtd": 2, "status": "confirmed",
                 "etag": '"e1"', "atualizado_origem": "2026-10-10T10:00:00.000Z", "privado": False}
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
        ga.listar_eventos("a@gmail.com", "primary", None, JANELA, Token(), http=_http([(status, {"error": SEGREDO})], []))
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


def test_cliente_so_faz_get_e_nao_tem_metodo_de_escrita():
    fonte = Path(ga.__file__).read_text()
    assert not re.search(r"""["'](POST|PUT|PATCH|DELETE)["']""", fonte)
    assert not re.search(r"events\.(insert|update|patch|delete|move|import|quickAdd)", fonte, re.I)
    assert not [n for n in dir(ga.GoogleAgenda) if n.lstrip("_").startswith(("criar", "apagar", "atualizar", "mover", "responder"))]


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
