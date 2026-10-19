import json
import re
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from gabi.fontes.graph_ness import ErroGraphNess, GraphNess

CONTA = "resper@ness.com.br"
EU = "11111111-1111-1111-1111-111111111111"
ANA = "22222222-2222-2222-2222-222222222222"
CHAT = "19:abc123@thread.v2"
NOW = 1760875200.0


class Token:
    def __init__(self):
        self.invalidacoes, self.n = 0, 0

    def __call__(self):
        self.n += 1
        return f"TOK{self.n}"

    def invalidar(self):
        self.invalidacoes += 1


class Falso:
    """`rotas`: lista de (método, regex do caminho decodificado, resposta | lista de respostas consumida em ordem). Chamada sem rota FALHA o teste."""

    def __init__(self, rotas):
        self.rotas = [(m, re.compile(p), r if isinstance(r, list) else [r]) for m, p, r in rotas]
        self.chamadas = []

    def __call__(self, metodo, url, corpo=None, cab=None):
        p = urlsplit(url)
        caminho = unquote(p.path)
        self.chamadas.append((metodo, caminho, parse_qs(p.query), corpo, cab))
        for m, rx, fila in self.rotas:
            if m == metodo and rx.search(caminho):
                return fila.pop(0) if len(fila) > 1 else fila[0]
        raise AssertionError(f"chamada não prevista: {metodo} {caminho}")


def graph(rotas, token=None):
    http = Falso(rotas)
    return GraphNess(token or Token(), [CONTA], http=http, agora=lambda: NOW), http


def eu_rota():
    return ("GET", r"/users/resper@ness\.com\.br$", (200, {"id": EU}))


def m(n, quando, de=ANA, nome="Ana", **kw):
    base = {"id": f"m{n}", "createdDateTime": quando, "messageType": "message", "deletedDateTime": None, "mentions": [],
            "from": {"user": {"id": de, "displayName": nome}, "application": None, "device": None},
            "body": {"content": "SEGREDO", "contentType": "text"}}
    base.update(kw)
    return base


def rota_msgs(itens):
    return ("GET", r"/chats/.+/messages$", (200, {"value": itens}))


def test_chats_mapeia_tipos_e_ultima():
    itens = [{"id": "c1", "chatType": "oneOnOne", "lastMessagePreview": {"createdDateTime": "2025-10-19T10:00:00.123Z", "body": {"content": "SEGREDO"}}},
             {"id": "c2", "chatType": "group", "lastMessagePreview": None},
             {"id": "c3", "chatType": "meeting", "lastMessagePreview": {"createdDateTime": "2025-10-18T09:00:00Z"}},
             {"id": "c4", "chatType": "outro"}]
    gr, http = graph([("GET", r"/users/resper@ness\.com\.br/chats$", (200, {"value": itens}))])
    r = gr.teams_chats(CONTA)
    assert r == [{"chat_id": "c1", "tipo": "um_a_um", "ultima_em": "2025-10-19T10:00:00+00:00"},
                 {"chat_id": "c2", "tipo": "grupo", "ultima_em": None},
                 {"chat_id": "c3", "tipo": "grupo", "ultima_em": "2025-10-18T09:00:00+00:00"}]
    assert "SEGREDO" not in json.dumps(r)
    assert http.chamadas[0][2]["$expand"] == ["lastMessagePreview"]


def test_mensagens_so_depois_de_desde_e_em_ordem():
    itens = [m(3, "2025-10-19T12:00:00Z"), m(2, "2025-10-19T11:00:00Z"), m(1, "2025-10-19T10:00:00Z")]
    gr, _ = graph([eu_rota(), rota_msgs(itens)])
    r = gr.teams_mensagens(CONTA, CHAT, "2025-10-19T10:00:00+00:00")
    assert [x["id"] for x in r] == ["m2", "m3"]
    assert r[0] == {"id": "m2", "quando": "2025-10-19T11:00:00+00:00", "de_nome": "Ana", "de_eu": False, "mencoes_eu": False}
    gr, _ = graph([eu_rota(), rota_msgs(itens)])
    assert [x["id"] for x in gr.teams_mensagens(CONTA, CHAT, None)] == ["m1", "m2", "m3"]


def test_ignora_sistema_apagada_e_bot():
    itens = [m(1, "2025-10-19T10:00:00Z", messageType="unknownFutureValue"),
             m(2, "2025-10-19T10:01:00Z", messageType="systemEventMessage"),
             m(3, "2025-10-19T10:02:00Z", deletedDateTime="2025-10-19T11:00:00Z"),
             m(4, "2025-10-19T10:03:00Z", **{"from": {"application": {"id": "bot", "displayName": "Bot"}, "user": None}}),
             m(5, "2025-10-19T10:04:00Z", **{"from": None}),
             m(6, "2025-10-19T10:05:00Z", **{"from": {"device": {"id": "d"}}}),
             m(7, "2025-10-19T10:06:00Z")]
    gr, _ = graph([eu_rota(), rota_msgs(itens)])
    assert [x["id"] for x in gr.teams_mensagens(CONTA, CHAT, None)] == ["m7"]


def test_de_eu_e_mencoes_eu_pelo_id_da_conta():
    ment = [{"id": 0, "mentionText": "x", "mentioned": {"user": {"id": EU, "displayName": "Ricardo"}}}]
    outra = [{"id": 0, "mentioned": {"user": {"id": ANA}}}, {"id": 1, "mentioned": {"conversation": {"id": "c"}}}, "lixo"]
    itens = [m(1, "2025-10-19T10:00:00Z", de=EU, nome="Ricardo"), m(2, "2025-10-19T10:01:00Z", mentions=ment),
             m(3, "2025-10-19T10:02:00Z", mentions=outra)]
    gr, http = graph([eu_rota(), rota_msgs(itens)])
    r = gr.teams_mensagens(CONTA, CHAT, None)
    assert [(x["de_eu"], x["mencoes_eu"]) for x in r] == [(True, False), (False, True), (False, False)]
    gr.teams_mensagens(CONTA, CHAT, None)  # o id da conta é cacheado
    assert sum(1 for c in http.chamadas if c[1].endswith("/resper@ness.com.br")) == 1


def test_conta_nao_cadastrada_levanta():
    gr, http = graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.teams_chats("outra@ness.com.br")
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.teams_mensagens("outra@ness.com.br", CHAT, None)
    assert http.chamadas == []


def test_chat_id_invalido_levanta():
    gr, http = graph([])
    for ruim in ("../x", "a b", "", "a/b", "x" * 201, None, 5):
        with pytest.raises(ErroGraphNess, match="chat inválido"):
            gr.teams_mensagens(CONTA, ruim, None)
    assert http.chamadas == []


def test_select_nao_pede_body():
    gr, http = graph([eu_rota(), rota_msgs([m(1, "2025-10-19T10:00:00Z")]),
                      ("GET", r"/chats$", (200, {"value": []}))])
    gr.teams_mensagens(CONTA, CHAT, None)
    gr.teams_chats(CONTA)
    msgs = next(c for c in http.chamadas if c[1].endswith("/messages"))
    assert msgs[2]["$select"] == ["id,createdDateTime,from,messageType,mentions,deletedDateTime"]
    assert msgs[2]["$orderby"] == ["createdDateTime desc"] and msgs[2]["$top"] == ["50"]
    for c in http.chamadas:
        for v in c[2].get("$select", []):
            assert "body" not in v and "subject" not in v and "attachments" not in v


def test_resposta_nao_traz_texto():
    gr, _ = graph([eu_rota(), rota_msgs([m(1, "2025-10-19T10:00:00Z")])])
    assert "SEGREDO" not in json.dumps(gr.teams_mensagens(CONTA, CHAT, None))


def test_erro_nao_vaza_corpo():
    gr, _ = graph([eu_rota(), ("GET", r"/messages$", (403, {"error": {"message": "TEXTO-SECRETO"}}))])
    with pytest.raises(ErroGraphNess) as e:
        gr.teams_mensagens(CONTA, CHAT, None)
    assert "TEXTO-SECRETO" not in repr(e.value) and "TOK" not in repr(e.value)
    gr, _ = graph([("GET", r"/chats$", (403, {"error": {"message": "TEXTO-SECRETO"}}))])
    with pytest.raises(ErroGraphNess, match="-> 403") as e:
        gr.teams_chats(CONTA)
    assert "TEXTO-SECRETO" not in repr(e.value)
