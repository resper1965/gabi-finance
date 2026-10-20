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


def test_so_leitura_no_codigo_fora_do_move():
    texto = Path(g.__file__).read_text()
    for proibido in ("PATCH", "PUT", "DELETE"):
        assert proibido not in texto
    assert texto.count('"POST"') == 2  # token e /move da lixeira (travado em test_graph_ness_email)


# ---------------- contatos ----------------
def _contato(**kw):
    return {"displayName": "Ana", "mobilePhone": None, "homePhones": [], "businessPhones": [], "emailAddresses": [], **kw}


def test_contatos_um_item_por_telefone_com_emails():
    c = _contato(mobilePhone="+55 11 99999-0000", homePhones=["1133334444"],
                 emailAddresses=[{"address": "Ana@X.com"}, {"address": "ana@x.com"}, {"address": "lixo"}])
    gr, _ = _graph([(200, {"value": [c]})])
    assert gr.contatos("resper@ness.com.br") == [
        {"nome": "Ana", "telefone": "+55 11 99999-0000", "emails": ["ana@x.com"]},
        {"nome": "Ana", "telefone": "1133334444", "emails": ["ana@x.com"]}]


def test_contatos_so_email_e_vazio():
    gr, _ = _graph([(200, {"value": [_contato(emailAddresses=[{"address": "ana@x.com"}]), _contato(displayName="Sem nada")]})])
    assert gr.contatos("resper@ness.com.br") == [{"nome": "Ana", "telefone": None, "emails": ["ana@x.com"]}]


def test_contatos_sem_email_nao_tem_chave_emails():
    gr, _ = _graph([(200, {"value": [_contato(mobilePhone="11999990000")]})])
    assert gr.contatos("resper@ness.com.br") == [{"nome": "Ana", "telefone": "11999990000"}]


def test_contatos_pagina_e_pede_so_campos_necessarios():
    prox = g.BASE + "/users/resper%40ness.com.br/contacts?$skiptoken=P2"
    gr, http = _graph([(200, {"value": [_contato(mobilePhone="1")], "@odata.nextLink": prox}), (200, {"value": [_contato(displayName="Bia", mobilePhone="2")]})])
    r = gr.contatos("resper@ness.com.br")
    assert [x["nome"] for x in r] == ["Ana", "Bia"]
    u = urlsplit(http.chamadas[0][1])
    assert u.path == "/v1.0/users/resper%40ness.com.br/contacts"
    q = parse_qs(u.query)
    assert q["$select"] == ["displayName,mobilePhone,homePhones,businessPhones,emailAddresses"] and q["$top"] == ["100"]
    assert http.chamadas[1][1] == prox


def test_contatos_paginacao_sem_fim():
    prox = g.BASE + "/users/resper%40ness.com.br/contacts?$skiptoken=P"
    gr, _ = _graph([(200, {"value": [], "@odata.nextLink": prox})] * 3)
    with pytest.raises(ErroGraphNess, match="paginação sem fim"):
        gr.contatos("resper@ness.com.br")
    gr, _ = _graph([(200, {"value": [], "@odata.nextLink": f"{prox}{i}"}) for i in range(g.MAX_PAGINAS + 5)])
    with pytest.raises(ErroGraphNess, match="paginação sem fim"):
        gr.contatos("resper@ness.com.br")


def test_contatos_conta_nao_permitida_sem_rede():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.contatos("outro@ness.com.br")
    assert http.chamadas == []


# ---------------- agenda ----------------
from gabi.agenda import tempo  # noqa: E402

JANELA = {"de": "2026-10-12T03:00:00+00:00", "ate": "2027-01-17T03:00:00+00:00"}
CONTA = "resper@ness.com.br"
PRIMEIRA = g.BASE + "/users/resper%40ness.com.br/calendarView/delta"


def _ev(id_="a", **kw):
    e = {"id": id_, "@odata.etag": 'W/"x"', "subject": "Reunião", "isAllDay": False, "isCancelled": False, "sensitivity": "normal", "showAs": "busy",
         "iCalUId": "uid-" + id_, "lastModifiedDateTime": "2026-10-10T10:00:00Z", "attendees": [],
         "start": {"dateTime": "2026-10-12T13:00:00.0000000", "timeZone": "UTC"}, "end": {"dateTime": "2026-10-12T14:00:00.0000000", "timeZone": "UTC"}}
    e.update(kw)
    return e


def test_calendarios():
    gr, http = _graph([(200, {"value": [{"id": "AAA=", "name": "Calendar", "isDefaultCalendar": True}, {"id": "BBB=", "name": "Feriados"}, {"name": "sem id"}]})])
    assert gr.listar_calendarios(CONTA) == [{"id": "AAA=", "nome": "Calendar", "principal": True}, {"id": "BBB=", "nome": "Feriados", "principal": False}]
    assert urlsplit(http.chamadas[0][1]).path == "/v1.0/users/resper%40ness.com.br/calendars"


def test_calendarios_conta_nao_permitida():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.listar_calendarios("outro@ness.com.br")
    assert http.chamadas == []


def test_eventos_carga_completa_pede_delta_com_janela():
    p2 = g.BASE + "/users/resper%40ness.com.br/calendarView/delta?$skiptoken=P2"
    delta = g.BASE + "/users/resper%40ness.com.br/calendarView/delta?$deltatoken=D1"
    gr, http = _graph([(200, {"value": [_ev("a")], "@odata.nextLink": p2}), (200, {"value": [_ev("b")], "@odata.deltaLink": delta})])
    r = gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert [e["externo_id"] for e in r["eventos"]] == ["a", "b"] and r["novo_sync_token"] == delta and r["recarga_completa"] is False
    u = urlsplit(http.chamadas[0][1])
    assert u.path == "/v1.0/users/resper%40ness.com.br/calendarView/delta"
    q = parse_qs(u.query)
    assert q["startDateTime"] == [JANELA["de"]] and q["endDateTime"] == [JANELA["ate"]]
    assert http.chamadas[0][3]["Prefer"] == 'outlook.timezone="UTC", odata.maxpagesize=200' and http.chamadas[1][1] == p2


def test_eventos_de_outro_calendario_usam_o_id_na_url():
    gr, http = _graph([(200, {"value": [], "@odata.deltaLink": g.BASE + "/x?$deltatoken=1"})])
    gr.listar_eventos(CONTA, "BBB=", None, JANELA)
    assert urlsplit(http.chamadas[0][1]).path == "/v1.0/users/resper%40ness.com.br/calendars/BBB%3D/calendarView/delta"


def test_eventos_incremental_usa_o_delta_link():
    link = g.BASE + "/users/resper%40ness.com.br/calendarView/delta?$deltatoken=abc"
    gr, http = _graph([(200, {"value": [_ev("a")], "@odata.deltaLink": g.BASE + "/x?$deltatoken=def"})])
    r = gr.listar_eventos(CONTA, "primary", link, JANELA)
    assert http.chamadas[0][1] == link and r["novo_sync_token"].endswith("def") and r["recarga_completa"] is False


def test_sync_token_de_outro_host_e_recusado():
    gr, http = _graph([])
    with pytest.raises(ErroGraphNess, match="token de sincronização inválido"):
        gr.listar_eventos(CONTA, "primary", "https://evil.example/d?$deltatoken=1", JANELA)
    assert http.chamadas == []


def test_mapeamento():
    gr, _ = _graph([(200, {"value": [
        _ev("comum", attendees=[{}, {}, {}], onlineMeeting={"joinUrl": "https://teams.microsoft.com/l/x"}),
        _ev("dia", isAllDay=True, start={"dateTime": "2026-10-12T00:00:00.0000000", "timeZone": "UTC"}, end={"dateTime": "2026-10-13T00:00:00.0000000", "timeZone": "UTC"}),
        _ev("http", onlineMeeting={"joinUrl": "http://x"}), _ev("priv", sensitivity="private"), _ev("livre", showAs="free"),
        _ev("semtitulo", subject=None)], "@odata.deltaLink": g.BASE + "/x?$deltatoken=1"})])
    ev = {e["externo_id"]: e for e in gr.listar_eventos(CONTA, "primary", None, JANELA)["eventos"]}
    c = ev["comum"]
    assert c["inicio"] == {"dateTime": "2026-10-12T13:00:00Z"} and c["fim"] == {"dateTime": "2026-10-12T14:00:00Z"}
    assert c["titulo"] == "Reunião" and c["participantes_qtd"] == 3 and c["link_reuniao"] == "https://teams.microsoft.com/l/x"
    assert c["status"] == "confirmed" and c["etag"] == 'W/"x"' and c["atualizado_origem"] == "2026-10-10T10:00:00Z" and c["ical_uid"] == "uid-comum"
    assert (c["privado"], c["livre"]) == (False, False)
    assert ev["dia"]["inicio"] == {"date": "2026-10-12"} and ev["dia"]["fim"] == {"date": "2026-10-13"}
    assert ev["http"]["link_reuniao"] is None and ev["priv"]["privado"] is True and ev["livre"]["livre"] is True and ev["semtitulo"]["titulo"] is None
    j = tempo.de_google(c["inicio"], c["fim"], "America/Sao_Paulo")
    assert j.dia_local == "2026-10-12" and not j.dia_inteiro
    d = tempo.de_google(ev["dia"]["inicio"], ev["dia"]["fim"], "America/Sao_Paulo")
    assert d.dia_inteiro and d.dia_local == "2026-10-12" and d.dia_fim_local == "2026-10-12"


def test_removido_cancelado_e_recusado_vao_para_cancelados():
    gr, _ = _graph([(200, {"value": [
        {"id": "r", "@removed": {"reason": "deleted"}}, _ev("c", isCancelled=True), _ev("d", responseStatus={"response": "declined"}),
        _ev("ok", responseStatus={"response": "accepted"})], "@odata.deltaLink": g.BASE + "/x?$deltatoken=1"})])
    r = gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert r["cancelados"] == ["r", "c", "d"] and [e["externo_id"] for e in r["eventos"]] == ["ok"]


def test_410_incremental_vira_recarga():
    link = g.BASE + "/users/resper%40ness.com.br/calendarView/delta?$deltatoken=velho"
    gr, http = _graph([(410, {}), (200, {"value": [_ev("a")], "@odata.deltaLink": g.BASE + "/x?$deltatoken=novo"})])
    r = gr.listar_eventos(CONTA, "primary", link, JANELA)
    assert r["recarga_completa"] is True and r["novo_sync_token"].endswith("novo") and len(http.chamadas) == 2
    assert "startDateTime" in http.chamadas[1][1]
    gr, _ = _graph([(410, {})])
    with pytest.raises(ErroGraphNess, match="-> 410"):
        gr.listar_eventos(CONTA, "primary", None, JANELA)


def test_429_nao_e_repetido():
    gr, http = _graph([(429, {})])
    with pytest.raises(ErroGraphNess, match="-> 429"):
        gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert len(http.chamadas) == 1


def test_eventos_pagina_sem_fim_e_link_de_outro_host():
    p = g.BASE + "/users/resper%40ness.com.br/calendarView/delta?$skiptoken=P"
    gr, _ = _graph([(200, {"value": [], "@odata.nextLink": p})] * 3)
    with pytest.raises(ErroGraphNess, match="paginação sem fim"):
        gr.listar_eventos(CONTA, "primary", None, JANELA)
    gr, http = _graph([(200, {"value": [], "@odata.nextLink": "https://evil.example/p"})])
    with pytest.raises(ErroGraphNess, match="link inválido"):
        gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert len(http.chamadas) == 1


def test_resposta_sem_delta_link_e_erro():
    gr, _ = _graph([(200, {"value": [_ev("a")]})])
    with pytest.raises(ErroGraphNess, match="resposta inválida do Graph"):
        gr.listar_eventos(CONTA, "primary", None, JANELA)


def test_calendario_e_janela_invalidos():
    gr, http = _graph([])
    for cal in ("a/b", "a b", "", None, "x" * 400):
        with pytest.raises(ErroGraphNess, match="calendário inválido"):
            gr.listar_eventos(CONTA, cal, None, JANELA)
    for jan in ({}, {"de": "x"}, None):
        with pytest.raises(ErroGraphNess, match="janela inválida"):
            gr.listar_eventos(CONTA, "primary", None, jan)
    assert http.chamadas == []


def test_evento_sem_id_e_pulado():
    gr, _ = _graph([(200, {"value": [{"subject": "x"}, {"id": 5}, _ev("ok")], "@odata.deltaLink": g.BASE + "/x?$deltatoken=1"})])
    r = gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert [e["externo_id"] for e in r["eventos"]] == ["ok"] and r["cancelados"] == []


def test_erro_nao_leva_titulo_do_evento():
    gr, _ = _graph([(500, {"error": {"message": "Reunião secreta"}})])
    with pytest.raises(ErroGraphNess) as e:
        gr.listar_eventos(CONTA, "primary", None, JANELA)
    assert "secreta" not in str(e.value)


# ---------------- redirecionamento ----------------
def test_http_real_nao_segue_redirecionamento_e_nao_vaza_o_bearer():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    vistos = []

    class Alvo(BaseHTTPRequestHandler):
        def do_GET(self):
            vistos.append(self.headers.get("Authorization"))
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    alvo = HTTPServer(("127.0.0.1", 0), Alvo)

    class Redireciona(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302); self.send_header("Location", f"http://127.0.0.1:{alvo.server_port}/roubo"); self.end_headers()

        def log_message(self, *a):
            pass

    origem = HTTPServer(("127.0.0.1", 0), Redireciona)
    for s in (alvo, origem):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        status, _ = g._http_real("GET", f"http://127.0.0.1:{origem.server_port}/x", None, {"Authorization": "Bearer TOKEN-SECRETO"})
    finally:
        for s in (alvo, origem):
            s.shutdown(); s.server_close()
    assert vistos == [] and status == 302


def test_get_trata_3xx_como_erro():
    gr, _ = _graph([(302, {})])
    with pytest.raises(ErroGraphNess, match="-> 302"):
        gr._get(g.BASE + "/users/x/y")
