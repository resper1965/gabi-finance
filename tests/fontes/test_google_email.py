import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from gabi.fontes import google_email as ge
from gabi.fontes.google_oauth import ErroGoogleOAuth

SEGREDO = "tok-SEGREDO-999"
ID = lambda n: f"{n:08x}"  # noqa: E731  ids do Gmail são hexadecimais


class Token:
    def __init__(self):
        self.invalidacoes, self.n = 0, 0

    def __call__(self, conta):
        self.n += 1
        return f"TOK{self.n}"

    def invalidar(self, conta):
        self.invalidacoes += 1


class Falso:
    """Servidor falso: `rotas` mapeia (método, caminho) -> lista de (status, corpo) consumida em ordem. Qualquer outra chamada FALHA o teste."""

    def __init__(self, rotas):
        self.rotas = {k: list(v) for k, v in rotas.items()}
        self.chamadas = []

    def __call__(self, metodo, url, corpo=None, cab=None):
        p = urlparse(url)
        self.chamadas.append((metodo, p.path, parse_qs(p.query), cab))
        caminho = re.sub(r"/messages/[0-9a-f]+", "/messages/{id}", p.path.replace("/gmail/v1/users/me", ""))
        fila = self.rotas.get((metodo, caminho))
        assert fila, f"chamada não prevista: {metodo} {caminho}"
        return fila.pop(0) if len(fila) > 1 else fila[0]


def _msg(n, de="Ana <ANA@x.com>", assunto="Reunião", rotulos=("INBOX",), extra=(), data=1760270400000, snippet="olá &amp; tchau"):
    cab = [{"name": "From", "value": de}, {"name": "Subject", "value": assunto}, *extra]
    return {"id": ID(n), "threadId": ID(n + 1000), "labelIds": list(rotulos), "internalDate": str(data), "snippet": snippet, "payload": {"headers": cab}}


def _carga(msgs, extra_rotas=None, hid="500"):
    rotas = {("GET", "/profile"): [(200, {"historyId": hid})],
             ("GET", "/messages"): [(200, {"messages": [{"id": m["id"]} for m in msgs]})],
             ("GET", "/messages/{id}"): [(200, m) for m in msgs] or [(404, {})]}
    rotas.update(extra_rotas or {})
    return Falso(rotas)


def test_carga_inicial_pega_so_inbox_na_janela_e_devolve_history_id():
    f = _carga([_msg(1), _msg(2, rotulos=("INBOX", "TRASH")), _msg(3, rotulos=("SENT",))])
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=f)
    assert [m["externo_id"] for m in r.mensagens] == [ID(1)] and r.novo_history_id == "500" and r.recarga_completa is False
    listagem = next(c for c in f.chamadas if c[1].endswith("/messages"))
    assert listagem[2]["q"] == ["in:inbox newer_than:14d"]
    assert f.chamadas[0][1].endswith("/profile")  # historyId lido ANTES de listar


def test_incremental_usa_history_e_so_mensagens_adicionadas_na_inbox():
    hist = {"history": [{"messagesAdded": [{"message": {"id": ID(1)}}, {"message": {"id": ID(2)}}]}, {"messagesAdded": [{"message": {"id": ID(1)}}]}], "historyId": "777"}
    f = Falso({("GET", "/history"): [(200, hist)], ("GET", "/messages/{id}"): [(200, _msg(1)), (200, _msg(2, rotulos=("INBOX", "SPAM")))]})
    r = ge.listar_novos("a@x.com", "500", 14, Token(), http=f)
    assert [m["externo_id"] for m in r.mensagens] == [ID(1)] and r.novo_history_id == "777"
    q = f.chamadas[0][2]
    assert q["startHistoryId"] == ["500"] and q["historyTypes"] == ["messageAdded"] and q["labelId"] == ["INBOX"]
    assert sum(1 for c in f.chamadas if "/messages/" in c[1]) == 2  # a mesma mensagem duas vezes no histórico é lida uma só


def test_history_404_recarrega_a_janela():
    f = Falso({("GET", "/history"): [(404, {})], ("GET", "/profile"): [(200, {"historyId": "900"})],
               ("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}]})], ("GET", "/messages/{id}"): [(200, _msg(1))]})
    r = ge.listar_novos("a@x.com", "1", 14, Token(), http=f)
    assert r.recarga_completa is True and r.novo_history_id == "900" and [m["externo_id"] for m in r.mensagens] == [ID(1)]


@pytest.mark.parametrize("extra,esperado", [
    ([{"name": "List-Unsubscribe", "value": "<mailto:x@y.com>"}], True),
    ([{"name": "Precedence", "value": "Bulk"}], True), ([{"name": "Precedence", "value": "list"}], True),
    ([{"name": "Auto-Submitted", "value": "auto-generated"}], True), ([{"name": "Auto-Submitted", "value": "no"}], False),
    ([{"name": "Precedence", "value": "normal"}], False), ([], False)])
def test_cabecalhos_de_lista_marcam_lista(extra, esperado):
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=_carga([_msg(1, extra=extra)]))
    assert r.mensagens[0]["lista"] is esperado


def test_remetente_vira_endereco_puro_minusculo_e_assunto_ausente_vira_vazio():
    m = _msg(1, de='"Ana, a Silva" <Ana.Silva@Empresa.COM>')
    m["payload"]["headers"] = [h for h in m["payload"]["headers"] if h["name"] != "Subject"]
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=_carga([m, _msg(2, de="lixo sem endereco")]))
    assert r.mensagens[0]["remetente"] == "ana.silva@empresa.com" and r.mensagens[0]["assunto"] == ""
    assert r.mensagens[1]["remetente"] == ""


def test_trecho_e_cortado_em_280_e_entidades_html_viram_texto():
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=_carga([_msg(1, snippet="a &amp; b " + "x" * 400)]))
    assert len(r.mensagens[0]["trecho"]) == 280 and r.mensagens[0]["trecho"].startswith("a & b ")


def test_data_em_epoch_vira_utc_e_mensagem_sem_data_e_pulada():
    ok, ruim = _msg(1, data=1760270400000), _msg(2)
    del ruim["internalDate"]
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=_carga([ok, ruim]))
    assert [m["recebida_em"] for m in r.mensagens] == ["2025-10-12T12:00:00+00:00"]


def test_pagina_sem_fim_e_erro_tipado_e_nunca_lista_parcial():
    pag = (200, {"messages": [{"id": ID(1)}], "nextPageToken": "P"})
    f = Falso({("GET", "/profile"): [(200, {"historyId": "1"})], ("GET", "/messages"): [pag], ("GET", "/messages/{id}"): [(200, _msg(1))]})
    with pytest.raises(ErroGoogleOAuth) as e:
        ge.listar_novos("a@x.com", None, 14, Token(), http=f)
    assert "paginação" in str(e.value)


def test_falha_numa_leitura_aborta_sem_resultado_parcial():
    f = Falso({("GET", "/profile"): [(200, {"historyId": "1"})], ("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}, {"id": ID(2)}]})],
               ("GET", "/messages/{id}"): [(200, _msg(1)), (500, {})]})
    with pytest.raises(ErroGoogleOAuth):
        ge.listar_novos("a@x.com", None, 14, Token(), http=f)


def test_mensagem_apagada_entre_listar_e_ler_e_ignorada():
    f = Falso({("GET", "/profile"): [(200, {"historyId": "1"})], ("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}, {"id": ID(2)}]})],
               ("GET", "/messages/{id}"): [(404, {}), (200, _msg(2))]})
    assert [m["externo_id"] for m in ge.listar_novos("a@x.com", None, 14, Token(), http=f).mensagens] == [ID(2)]


def test_401_invalida_o_token_e_repete_uma_vez():
    t = Token()
    f = Falso({("GET", "/profile"): [(401, {}), (200, {"historyId": "1"})], ("GET", "/messages"): [(200, {})]})
    r = ge.listar_novos("a@x.com", None, 14, t, http=f)
    assert t.invalidacoes == 1 and r.mensagens == [] and f.chamadas[0][3] != f.chamadas[1][3]


def test_lixeira_e_restaurar_sao_por_id_e_falha_de_um_nao_aborta_o_lote():
    f = Falso({("POST", "/messages/{id}/trash"): [(200, {}), (403, {}), (200, {})], ("POST", "/messages/{id}/untrash"): [(200, {})]})
    assert ge.lixeira("a@x.com", [ID(1), ID(2), ID(3)], Token(), http=f) == {ID(1): "ok", ID(2): "erro", ID(3): "ok"}
    assert ge.restaurar("a@x.com", [ID(1)], Token(), http=f) == {ID(1): "ok"}
    assert [c[0] for c in f.chamadas] == ["POST"] * 4


def test_erro_de_rede_num_id_vira_erro_so_naquele_id():
    n = {"i": 0}

    def http(m, url, corpo=None, cab=None):
        n["i"] += 1
        if n["i"] == 1:
            raise ErroGoogleOAuth("Google indisponível: TimeoutError")
        return 200, {}
    assert ge.lixeira("a@x.com", [ID(1), ID(2)], Token(), http=http) == {ID(1): "erro", ID(2): "ok"}


def test_ids_invalidos_e_lote_grande_sao_recusados_sem_chamar_o_google():
    nunca = lambda *a, **k: pytest.fail("não deveria chamar")  # noqa: E731
    for ruim in (["../x"], ["ZZ"], [""], [3], "abc"):
        with pytest.raises(ErroGoogleOAuth):
            ge.lixeira("a@x.com", ruim, Token(), http=nunca)
    with pytest.raises(ErroGoogleOAuth):
        ge.lixeira("a@x.com", [ID(i) for i in range(101)], Token(), http=nunca)


def test_enviados_recentes_junta_to_e_cc_sem_repetir():
    def env(n, to, cc=""):
        return {"id": ID(n), "payload": {"headers": [{"name": "To", "value": to}, {"name": "Cc", "value": cc}]}}
    f = Falso({("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}, {"id": ID(2)}]})],
               ("GET", "/messages/{id}"): [(200, env(1, "Bia <Bia@X.com>, c@y.com", "d@z.com")), (200, env(2, "bia@x.com; e@w.com"))]})
    assert ge.enviados_recentes("a@x.com", 365, Token(), http=f) == ["bia@x.com", "c@y.com", "d@z.com", "e@w.com"]
    assert f.chamadas[0][2]["q"] == ["in:sent newer_than:365d"]
    assert f.chamadas[1][2]["metadataHeaders"] == ["To", "Cc"]


def test_enviados_recentes_le_no_maximo_200_cabecalhos():
    ids = [{"id": ID(i)} for i in range(1, 601)]
    paginas = [(200, {"messages": ids[i:i + 100], "nextPageToken": f"P{i}"}) for i in range(0, 600, 100)]
    f = Falso({("GET", "/messages"): paginas, ("GET", "/messages/{id}"): [(200, {"id": ID(1), "payload": {"headers": []}})]})
    ge.enviados_recentes("a@x.com", 365, Token(), http=f)
    assert sum(1 for c in f.chamadas if "/messages/" in c[1]) == 200  # trabalho limitado: a ponte tem 130 s por chamada


def test_entradas_invalidas_sao_erro_tipado_sem_chamar_o_google():
    nunca = lambda *a, **k: pytest.fail("não deveria chamar")  # noqa: E731
    for args in (("conta ruim", None, 14), ("a@x.com", None, 0), ("a@x.com", None, 400), ("a@x.com", "abc", 14), ("a@x.com", None, True)):
        with pytest.raises(ErroGoogleOAuth):
            ge.listar_novos(*args, Token(), http=nunca)
    with pytest.raises(ErroGoogleOAuth):
        ge.enviados_recentes("a@x.com", 0, Token(), http=nunca)


def test_erro_nao_leva_segredo_nem_corpo():
    f = Falso({("GET", "/profile"): [(500, {"error": SEGREDO})]})
    with pytest.raises(ErroGoogleOAuth) as e:
        ge.listar_novos("a@x.com", None, 14, Token(), http=f)
    assert SEGREDO not in str(e.value) and str(e.value) == "profile -> 500"


def test_cliente_so_faz_get_e_post_de_trash_untrash():
    fonte = Path(ge.__file__).read_text()
    assert set(re.findall(r"""["'](POST|PUT|PATCH|DELETE)["']""", fonte)) == {"POST"}
    codigo = fonte.replace(ge.ESCOPO, "").replace("gmail.modify", "")
    for proibido in (r"\.send\b", r"/send\b", r"drafts", r"batchDelete", r"batchModify", r"/delete", r"\.delete\b", r"\.modify\b", r"/modify\b", r"labels"):
        assert not re.search(proibido, codigo, re.I), proibido
    assert not [n for n in dir(ge.GoogleEmail) if n.lstrip("_").startswith(("enviar", "responder", "apagar", "rascunho", "rotular"))]
    assert sorted(m for m in dir(ge.GoogleEmail) if not m.startswith("_")) == ["enviados_recentes", "listar_novos", "lixeira", "mensagem", "respondeu_a", "restaurar"]


def test_objeto_da_ponte_devolve_json_puro_e_sem_credencial_e_none():
    g = ge.GoogleEmail(Token(), http=_carga([_msg(1)]))
    r = g.listar_novos("a@x.com", None, 14)
    assert isinstance(r, dict) and set(r) == {"mensagens", "novo_history_id", "recarga_completa"}
    assert ge.google_email_do_ambiente({}) is None
    assert ge.google_email_do_ambiente({"GOOGLE_CLIENT_ID": "i", "GOOGLE_CLIENT_SECRET": "s"}) is not None
    assert "SEGREDO" not in repr(g) and "TOK" not in repr(g)


def test_carga_grande_le_so_as_mais_recentes_para_caber_no_tempo_da_ponte():
    ids = [{"id": ID(i)} for i in range(1, 451)]  # o Gmail lista a mais nova primeiro
    paginas = [(200, {"messages": ids[i:i + 100], **({"nextPageToken": f"P{i}"} if i < 400 else {})}) for i in range(0, 450, 100)]
    f = Falso({("GET", "/profile"): [(200, {"historyId": "9"})], ("GET", "/messages"): paginas, ("GET", "/messages/{id}"): [(200, _msg(1))]})
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=f)
    lidas = [c[1] for c in f.chamadas if re.search(r"/messages/[0-9a-f]+$", c[1])]
    assert len(lidas) == ge.MAX_CARGA_MSGS == 200 and lidas[0].endswith(ID(1)) and lidas[-1].endswith(ID(200))
    assert r.novo_history_id == "9"


def test_incremental_com_mais_de_200_novas_cai_na_carga_limitada_e_avisa_que_recarregou():
    hist = {"history": [{"messagesAdded": [{"message": {"id": ID(i)}} for i in range(1, 251)]}], "historyId": "777"}
    f = Falso({("GET", "/history"): [(200, hist)], ("GET", "/profile"): [(200, {"historyId": "900"})],
               ("GET", "/messages"): [(200, {"messages": [{"id": ID(i)} for i in range(1, 51)]})], ("GET", "/messages/{id}"): [(200, _msg(1))]})
    r = ge.listar_novos("a@x.com", "500", 14, Token(), http=f)
    assert r.recarga_completa is True and r.novo_history_id == "900"
    assert not any(c[1].endswith(ID(201)) for c in f.chamadas)  # nunca passou do teto


def test_respondeu_a_pergunta_ao_gmail_endereco_por_endereco():
    f = Falso({("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}]}), (200, {"resultSizeEstimate": 0})]})
    r = ge.respondeu_a("a@x.com", ["Bia@X.com", "c@y.com"], Token(), http=f)
    assert r == {"bia@x.com": True, "c@y.com": False}
    assert f.chamadas[0][2]["q"] == ["in:sent to:bia@x.com"] and f.chamadas[0][2]["maxResults"] == ["1"]


def test_respondeu_a_erro_do_gmail_e_erro_tipado_nunca_falso():
    f = Falso({("GET", "/messages"): [(500, {})]})
    with pytest.raises(ErroGoogleOAuth):
        ge.respondeu_a("a@x.com", ["bia@x.com"], Token(), http=f)


def test_respondeu_a_recusa_endereco_invalido_e_lote_grande_sem_chamar_o_google():
    nunca = lambda *a, **k: pytest.fail("não deveria chamar")  # noqa: E731
    for ruim in (["nao e email"], ['a@x.com" OR in:inbox'], [3], "bia@x.com", ["a@x.com"] * 0 + [f"u{i}@x.com" for i in range(21)]):
        with pytest.raises(ErroGoogleOAuth):
            ge.respondeu_a("a@x.com", ruim, Token(), http=nunca)


def test_mensagem_veneno_4xx_e_pulada_e_as_outras_entram():
    rotas = {("GET", "/profile"): [(200, {"historyId": "500"})],
             ("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}, {"id": ID(2)}, {"id": ID(3)}]})],
             ("GET", "/messages/{id}"): [(200, _msg(1)), (400, {}), (200, _msg(3))]}
    r = ge.listar_novos("a@x.com", None, 14, Token(), http=Falso(rotas))
    assert [m["externo_id"] for m in r.mensagens] == [ID(1), ID(3)]


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_status_de_credencial_cota_ou_servidor_ainda_para_a_leitura(status):
    rotas = {("GET", "/profile"): [(200, {"historyId": "500"})],
             ("GET", "/messages"): [(200, {"messages": [{"id": ID(1)}]})],
             ("GET", "/messages/{id}"): [(status, {})]}
    with pytest.raises(ErroGoogleOAuth, match=str(status)):
        ge.listar_novos("a@x.com", None, 14, Token(), http=Falso(rotas))


@pytest.mark.parametrize("acao", ["delete", "modify", "batchDelete", "trash/../delete", "", "TRASH"])
def test_mover_so_aceita_trash_e_untrash(acao):
    nunca = lambda *a, **k: pytest.fail("não deveria chamar")  # noqa: E731
    with pytest.raises(ErroGoogleOAuth):
        ge._mover("a@x.com", [ID(1)], acao, Token(), nunca)


# ---- Onda 2: corpo da mensagem (só leitura) ----
import base64  # noqa: E402


def _b64(t):
    return base64.urlsafe_b64encode(t.encode()).decode().rstrip("=")


def _full(partes, mime="multipart/alternative"):
    return {"id": ID(7), "payload": {"mimeType": mime, "headers": [], "parts": partes}}


def _corpo(resp, status=200):
    f = Falso({("GET", "/messages/{id}"): [(status, resp)]})
    return ge.mensagem("a@x.com", ID(7), Token(), f), f


def test_mensagem_texto_plano():
    r, f = _corpo(_full([{"mimeType": "text/plain", "body": {"data": _b64("Olá ")}}, {"mimeType": "text/plain", "body": {"data": _b64("mundo")}},
                         {"mimeType": "text/html", "body": {"data": _b64("<p>outro</p>")}}]))
    assert r == {"corpo": "Olá\nmundo", "cortado": False}
    assert f.chamadas[0][0] == "GET" and f.chamadas[0][2]["format"] == ["full"]


def test_mensagem_so_html():
    r, _ = _corpo(_full([{"mimeType": "text/html", "body": {"data": _b64("<style>x</style><p>Oi</p><script>y</script>")}}]))
    assert r == {"corpo": "Oi", "cortado": False}


def test_mensagem_corta_em_8000():
    r, _ = _corpo(_full([{"mimeType": "text/plain", "body": {"data": _b64("a" * 9000)}}]))
    assert len(r["corpo"]) == 8000 and r["cortado"] is True


def test_mensagem_id_invalido_e_404_e_erro_da_fonte():
    with pytest.raises(ErroGoogleOAuth):
        ge.mensagem("a@x.com", "../x", Token(), Falso({}))
    with pytest.raises(ErroGoogleOAuth, match="mensagem não encontrada"):
        _corpo({}, 404)
    with pytest.raises(ErroGoogleOAuth):
        _corpo({}, 500)


def test_classe_google_email_expoe_mensagem():
    f = Falso({("GET", "/messages/{id}"): [(200, _full([{"mimeType": "text/plain", "body": {"data": _b64("x")}}]))]})
    assert ge.GoogleEmail(Token(), f).mensagem("a@x.com", ID(7)) == {"corpo": "x", "cortado": False}


def test_mensagem_ignora_anexo_de_texto():
    r, _ = _corpo(_full([{"mimeType": "text/plain", "body": {"data": _b64("corpo")}},
                         {"mimeType": "text/plain", "filename": "notas.txt", "body": {"data": _b64("anexo")}}]))
    assert r == {"corpo": "corpo", "cortado": False}


def test_get_repete_503_e_post_nao_repete():
    f = Falso({("GET", "/profile"): [(503, {}), (200, {"historyId": "1"})], ("GET", "/messages"): [(200, {})]})
    assert ge.listar_novos("a@x.com", None, 14, Token(), http=f).mensagens == []
    assert [c[0] for c in f.chamadas].count("GET") == 3  # profile 503, profile 200, messages
    f = Falso({("POST", "/messages/{id}/trash"): [(503, {})]})
    assert ge.lixeira("a@x.com", [ID(1)], Token(), http=f) == {ID(1): "erro"}
    assert len(f.chamadas) == 1
