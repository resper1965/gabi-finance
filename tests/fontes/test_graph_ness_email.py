import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from gabi.fontes import graph_ness as g
from gabi.fontes.graph_ness import ErroGraphNess, GraphNess

CONTA = "resper@ness.com.br"
HOST = "https://graph.microsoft.com/v1.0"
DELTA = "https://graph.microsoft.com/v1.0/users/x/mailFolders/inbox/messages/delta?$deltatoken=D1"
NOW = 1760875200.0  # 2025-10-19T12:00:00Z


def mid(n):
    return f"AAMk{n:08d}="


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


def msg(n, de="Ana <x>", assunto="Reunião", recebida="2025-10-19T10:00:00Z", **kw):
    base = {"id": mid(n), "conversationId": f"conv{n}", "from": {"emailAddress": {"address": "ANA@x.com", "name": "Ana"}},
            "subject": assunto, "receivedDateTime": recebida, "bodyPreview": "olá\n  tchau", "isDraft": False, "internetMessageHeaders": []}
    base.update(kw)
    return base


def carga(msgs, delta=DELTA):
    return [("GET", r"/mailFolders/inbox/messages/delta$", (200, {"value": [{"id": m["id"], "receivedDateTime": m["receivedDateTime"]} for m in msgs],
                                                                  "@odata.deltaLink": delta})),
            ("GET", r"/messages/AAMk", [(200, m) for m in msgs] or [(404, {})])]


def test_carga_inicial_filtra_pela_janela_e_devolve_o_delta_como_history_id():
    gr, http = graph(carga([msg(1), msg(2, isDraft=True)]))
    r = gr.listar_novos(CONTA, None, 14)
    assert [m["externo_id"] for m in r["mensagens"]] == [mid(1)]
    assert r["novo_history_id"] == DELTA and r["recarga_completa"] is False
    delta = next(c for c in http.chamadas if c[1].endswith("/delta"))
    assert delta[2]["$filter"] == ["receivedDateTime ge 2025-10-05T12:00:00Z"]
    assert 'IdType="ImmutableId"' in delta[4]["Prefer"]


def test_mensagem_mapeada_sem_corpo_e_com_sinal_de_lista():
    cab = [{"name": "List-Unsubscribe", "value": "<mailto:x@y.com>"}]
    gr, _ = graph(carga([msg(1, internetMessageHeaders=cab, subject="S" * 500)]))
    m = gr.listar_novos(CONTA, None, 14)["mensagens"][0]
    assert m == {"externo_id": mid(1), "thread_id": "conv1", "remetente": "ana@x.com", "assunto": "S" * 300,
                 "recebida_em": "2025-10-19T10:00:00+00:00", "trecho": "olá tchau", "lista": True}


def test_pede_so_campos_curtos_nunca_o_corpo():
    gr, http = graph(carga([msg(1)]))
    gr.listar_novos(CONTA, None, 14)
    leitura = next(c for c in http.chamadas if "/messages/AAMk" in c[1])
    campos = leitura[2]["$select"][0].split(",")
    assert "body" not in campos and "bodyPreview" in campos


def test_incremental_usa_o_delta_guardado_e_pula_removidos():
    novo = "https://graph.microsoft.com/v1.0/users/x/mailFolders/inbox/messages/delta?$deltatoken=D2"
    gr, http = graph([("GET", r"/delta$", (200, {"value": [{"id": mid(1)}, {"id": mid(9), "@removed": {"reason": "deleted"}}],
                                                "@odata.deltaLink": novo})),
                      ("GET", r"/messages/AAMk", (200, msg(1)))])
    r = gr.listar_novos(CONTA, DELTA, 14)
    assert [m["externo_id"] for m in r["mensagens"]] == [mid(1)] and r["novo_history_id"] == novo
    assert sum(1 for c in http.chamadas if "/messages/AAMk" in c[1]) == 1


def test_delta_expirado_410_vira_recarga_completa():
    gr, http = graph([("GET", r"/delta$", [(410, {}), (200, {"value": [{"id": mid(1), "receivedDateTime": "2025-10-19T10:00:00Z"}],
                                                          "@odata.deltaLink": DELTA})]),
                      ("GET", r"/messages/AAMk", (200, msg(1)))])
    r = gr.listar_novos(CONTA, DELTA, 14)
    assert r["recarga_completa"] is True and len(r["mensagens"]) == 1


def test_muita_coisa_de_uma_vez_recarrega_so_as_mais_recentes():
    muitos = [{"id": mid(i), "receivedDateTime": f"2025-10-19T10:{i % 60:02d}:00Z"} for i in range(250)]
    gr, http = graph([("GET", r"/delta$", [(200, {"value": muitos, "@odata.deltaLink": DELTA}), (200, {"value": muitos, "@odata.deltaLink": DELTA})]),
                      ("GET", r"/messages/AAMk", (200, msg(1)))])
    r = gr.listar_novos(CONTA, DELTA, 14)
    assert r["recarga_completa"] is True
    assert sum(1 for c in http.chamadas if "/messages/AAMk" in c[1]) == g.MAX_CARGA_MSGS


def test_id_com_erro_4xx_so_dele_e_pulado_mas_403_para_tudo():
    gr, _ = graph([("GET", r"/delta$", (200, {"value": [{"id": mid(1), "receivedDateTime": "x"}, {"id": mid(2), "receivedDateTime": "x"}],
                                              "@odata.deltaLink": DELTA})),
                   ("GET", r"/messages/AAMk", [(404, {}), (200, msg(2))])])
    assert [m["externo_id"] for m in gr.listar_novos(CONTA, None, 14)["mensagens"]] == [mid(2)]
    gr, _ = graph([("GET", r"/delta$", (200, {"value": [{"id": mid(1), "receivedDateTime": "x"}], "@odata.deltaLink": DELTA})),
                   ("GET", r"/messages/AAMk", (403, {}))])
    with pytest.raises(ErroGraphNess, match="-> 403"):
        gr.listar_novos(CONTA, None, 14)


def test_delta_guardado_de_outro_host_nao_sai_com_o_token():
    gr, http = graph([])
    with pytest.raises(ErroGraphNess, match="token de sincronização inválido"):
        gr.listar_novos(CONTA, "https://evil.example/delta", 14)
    assert http.chamadas == []


def test_conta_e_janela_invalidas_sem_rede():
    gr, http = graph([])
    with pytest.raises(ErroGraphNess, match="conta não permitida"):
        gr.listar_novos("outra@ness.com.br", None, 14)
    for janela in (0, 366, True, "14"):
        with pytest.raises(ErroGraphNess, match="janela inválida"):
            gr.listar_novos(CONTA, None, janela)
    assert http.chamadas == []


# ---------------- lixeira ----------------
def test_lixeira_move_para_itens_excluidos_e_restaurar_para_a_entrada():
    gr, http = graph([("POST", r"/messages/.+/move$", [(201, {}), (500, {})])])
    assert gr.lixeira(CONTA, [mid(1), mid(2)]) == {mid(1): "ok", mid(2): "erro"}
    assert [json.loads(c[3]) for c in http.chamadas] == [{"destinationId": "deleteditems"}] * 2
    gr, http = graph([("POST", r"/messages/.+/move$", (200, {}))])
    assert gr.restaurar(CONTA, [mid(1)]) == {mid(1): "ok"}
    assert json.loads(http.chamadas[0][3]) == {"destinationId": "inbox"}
    assert 'IdType="ImmutableId"' in http.chamadas[0][4]["Prefer"]


def test_lixeira_valida_ids_e_lote_antes_de_qualquer_rede():
    gr, http = graph([])
    for ruim in (["../x"], ["a b" * 5], [""], [1], "texto"):
        with pytest.raises(ErroGraphNess):
            gr.lixeira(CONTA, ruim)
    with pytest.raises(ErroGraphNess, match="no máximo"):
        gr.lixeira(CONTA, [mid(i) for i in range(101)])
    with pytest.raises(ErroGraphNess, match="ação não permitida"):
        gr._mover(CONTA, [mid(1)], "delete")
    assert http.chamadas == []


def test_401_no_move_invalida_o_token_e_repete_uma_vez():
    tok = Token()
    gr, http = graph([("POST", r"/move$", [(401, {}), (200, {})])], token=tok)
    assert gr.lixeira(CONTA, [mid(1)]) == {mid(1): "ok"} and tok.invalidacoes == 1 and len(http.chamadas) == 2


# ---------------- enviados e "já respondi" ----------------
def test_enviados_recentes_junta_to_e_cc_sem_repetir():
    pagina = {"value": [{"toRecipients": [{"emailAddress": {"address": "Ana@X.com"}}], "ccRecipients": [{"emailAddress": {"address": "bia@x.com"}}]},
                        {"toRecipients": [{"emailAddress": {"address": "ana@x.com"}}], "ccRecipients": []}]}
    gr, http = graph([("GET", r"/mailFolders/sentitems/messages$", (200, pagina))])
    assert gr.enviados_recentes(CONTA, 365) == ["ana@x.com", "bia@x.com"]
    assert http.chamadas[0][2]["$filter"] == ["sentDateTime ge 2024-10-19T12:00:00Z"]


def test_respondeu_a_consulta_exata_to_e_cc_e_erro_nao_vira_nao_respondeu():
    gr, http = graph([("GET", r"/sentitems/messages$", [(200, {"value": []}), (200, {"value": [{"id": "1"}]}),
                                                         (200, {"value": []}), (200, {"value": []})])])
    assert gr.respondeu_a(CONTA, ["ana@x.com", "bia@x.com"]) == {"ana@x.com": True, "bia@x.com": False}
    filtros = [c[2]["$filter"][0] for c in http.chamadas]
    assert filtros[0] == "toRecipients/any(r:r/emailAddress/address eq 'ana@x.com')"
    assert filtros[1].startswith("ccRecipients/any(")
    gr, _ = graph([("GET", r"/sentitems/messages$", (503, {}))])
    with pytest.raises(ErroGraphNess, match="-> 503"):
        gr.respondeu_a(CONTA, ["ana@x.com"])


def test_respondeu_a_escapa_apostrofo_no_filtro():
    gr, http = graph([("GET", r"/sentitems/messages$", (200, {"value": []}))])
    gr.respondeu_a(CONTA, ["o'neil@x.com"])
    assert http.chamadas[0][2]["$filter"] == ["toRecipients/any(r:r/emailAddress/address eq 'o''neil@x.com')"]


def test_respondeu_a_recusa_endereco_que_nao_e_endereco():
    gr, http = graph([])
    for ruim in ("ana@x", "ana x@x.com", "a@b@x.com"):
        with pytest.raises(ErroGraphNess, match="endereço inválido"):
            gr.respondeu_a(CONTA, [ruim])
    with pytest.raises(ErroGraphNess, match="endereços por chamada"):
        gr.respondeu_a(CONTA, [])
    assert http.chamadas == []


# ---------------- trava no código ----------------
def test_so_dois_posts_e_nenhum_metodo_de_enviar_ou_apagar():
    texto = Path(g.__file__).read_text()
    assert texto.count('"POST"') == 2  # o do token e o do /move
    for proibido in ("PATCH", "PUT", "DELETE", "sendMail", "/send", "/forward", "/reply", "createReply", "createForward", "permanentDelete"):
        assert proibido not in texto
    assert set(g._DESTINOS.values()) == {"deleteditems", "inbox"}
    for metodo in ("enviar", "responder", "encaminhar", "apagar", "send", "reply", "delete", "rascunho"):
        assert not hasattr(GraphNess, metodo)


def test_erro_nunca_leva_texto_de_email_nem_segredo():
    gr, _ = graph([("GET", r"/delta$", (200, {"value": [{"id": mid(1), "receivedDateTime": "x"}], "@odata.deltaLink": DELTA})),
                   ("GET", r"/messages/AAMk", (500, {"error": {"message": "ASSUNTO-SECRETO"}}))])
    with pytest.raises(ErroGraphNess) as e:
        gr.listar_novos(CONTA, None, 14)
    assert "ASSUNTO-SECRETO" not in repr(e.value) and "TOK" not in repr(e.value)


# ---- Onda 2: corpo da mensagem (só leitura) ----
def test_mensagem_graph_prefer_texto():
    gr, http = graph([("GET", r"/messages/AAMk", (200, {"id": mid(1), "body": {"contentType": "text", "content": "Olá\nmundo"}}))])
    assert gr.mensagem(CONTA, mid(1)) == {"corpo": "Olá\nmundo", "cortado": False}
    c = http.chamadas[0]
    assert c[0] == "GET" and c[2]["$select"] == ["body"]
    assert 'outlook.body-content-type="text"' in c[4]["Prefer"] and 'IdType="ImmutableId"' in c[4]["Prefer"]


def test_mensagem_graph_html_vira_texto_e_corta():
    gr, _ = graph([("GET", r"/messages/AAMk", (200, {"body": {"contentType": "html", "content": "<style>x</style><p>Oi</p>"}}))])
    assert gr.mensagem(CONTA, mid(1))["corpo"] == "Oi"
    gr, _ = graph([("GET", r"/messages/AAMk", (200, {"body": {"contentType": "text", "content": "b" * 9000}}))])
    r = gr.mensagem(CONTA, mid(1))
    assert len(r["corpo"]) == 8000 and r["cortado"] is True


def test_mensagem_graph_id_invalido_404_e_forma():
    gr, _ = graph([])
    with pytest.raises(ErroGraphNess):
        gr.mensagem(CONTA, "a/b")
    gr, _ = graph([("GET", r"/messages/AAMk", (404, {}))])
    with pytest.raises(ErroGraphNess, match="mensagem não encontrada"):
        gr.mensagem(CONTA, mid(1))
    gr, _ = graph([("GET", r"/messages/AAMk", (200, {"body": "x"}))])
    with pytest.raises(ErroGraphNess):
        gr.mensagem(CONTA, mid(1))


# ---------------- enviados_textos (ADR-037) ----------------
def test_enviados_textos_devolve_trecho_sem_citacao_e_converte_html():
    pagina = {"value": [
        {"id": mid(1), "subject": "Proposta", "sentDateTime": "2025-10-18T10:00:00Z", "toRecipients": [{"emailAddress": {"address": "Ana@X.com"}}],
         "body": {"contentType": "text", "content": "Te mando até sexta.\n\nDe: Ana\nEnviado: ontem\n> velho"}},
        {"id": mid(2), "subject": "Oi", "sentDateTime": "2025-10-17T10:00:00Z", "toRecipients": [],
         "body": {"contentType": "html", "content": "<p>Ligo amanhã</p>"}}]}
    gr, http = graph([("GET", r"/mailFolders/sentitems/messages$", (200, pagina))])
    r = gr.enviados_textos(CONTA, 7, 10)
    assert r[0] == {"externo_id": mid(1), "quando": "2025-10-18T10:00:00Z", "para": ["ana@x.com"], "assunto": "Proposta", "trecho": "Te mando até sexta."}
    assert r[1]["trecho"] == "Ligo amanhã"
    assert http.chamadas[0][2]["$filter"] == ["sentDateTime ge 2025-10-12T12:00:00Z"]
    assert 'outlook.body-content-type="text"' in http.chamadas[0][4]["Prefer"]


def test_enviados_textos_limite_e_entradas_invalidas():
    gr, _ = graph([("GET", r"/sentitems/messages$", (200, {"value": [{"id": mid(i), "body": {"content": "x"}} for i in range(1, 9)]}))])
    assert len(gr.enviados_textos(CONTA, 7, 3)) == 3
    for dias, limite in ((0, 5), (15, 5), (7, 0), (7, 31), (True, 5)):
        with pytest.raises(ErroGraphNess):
            gr.enviados_textos(CONTA, dias, limite)
