import inspect
import json
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gabi.fontes import google as gmod, graph as grmod
from gabi.fontes.google import Google
from gabi.fontes.graph import Graph


class Servidor:
    """Servidor falso: registra chamadas e devolve respostas enfileiradas por trecho de URL."""
    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, url, corpo, cabecalhos or {}))
        for trecho, resp in self.respostas.items():
            if trecho in url:
                r = resp.pop(0) if isinstance(resp, list) else resp
                return r if isinstance(r, tuple) else (200, r)
        return 404, {}


# ---- Graph ----
def test_graph_delta_so_traz_mudancas_desde_o_ultimo_token():
    srv = Servidor({"/messages/delta": [{"value": [{"internetMessageId": "<1>", "from": {"emailAddress": {"address": "a@x.com"}}, "subject": "Oi",
                                                    "receivedDateTime": "2026-10-09T10:00:00Z", "bodyPreview": "olá"}],
                                         "@odata.deltaLink": "https://graph/x/messages/delta?$deltatoken=T2"}]})
    g = Graph(token=lambda: "tk", http=srv)
    msgs, tok = g.delta_mensagens("a@x.com", "https://graph/x/messages/delta?$deltatoken=T1")
    assert "T1" in srv.chamadas[0][1]            # parte do último token, não do começo
    assert tok.endswith("T2")
    assert msgs[0] == {"message_id": "<1>", "remetente": "a@x.com", "assunto": "Oi", "recebido_em": "2026-10-09T10:00:00Z", "trecho": "olá"}


def test_graph_segue_nextlink_ate_o_fim():
    srv = Servidor({"/messages/delta": [{"value": [], "@odata.nextLink": "https://graph/p2/messages/delta?x"},
                                        {"value": [], "@odata.deltaLink": "https://graph/z?$deltatoken=F"}]})
    _, tok = Graph(token=lambda: "tk", http=srv).delta_mensagens("a@x.com", None)
    assert len(srv.chamadas) == 2 and tok.endswith("F")


def test_graph_criar_rascunho_nao_chama_send():
    srv = Servidor({"/messages": {"id": "r1"}})
    rid = Graph(token=lambda: "tk", http=srv).criar_rascunho("a@x.com", ["b@x.com"], "Assunto", "Corpo")
    assert rid == "r1"
    assert all("send" not in c[1].lower() for c in srv.chamadas)
    assert not [n for n in dir(Graph) if "send" in n.lower() or "enviar" in n.lower()]


def test_graph_nao_tem_metodo_de_exclusao():
    assert not [n for n in dir(Graph) if n.lstrip("_").startswith(("delete", "apagar", "excluir", "remover"))]
    assert "DELETE" not in inspect.getsource(grmod)


def test_graph_erro_nao_vaza_token():
    g = Graph(token=lambda: "segredo-123", http=Servidor({"/messages/delta": [(403, {"error": {"message": "negado"}})]}))
    with pytest.raises(grmod.ErroGraph) as e:
        g.delta_mensagens("a@x.com", None)
    assert "segredo-123" not in str(e.value)


def test_graph_pedido_de_aprovacao_do_admin_gera_link_copiavel():
    link = grmod.link_aprovacao_admin("tenant-1", "app-1")
    assert link.startswith("https://login.microsoftonline.com/tenant-1/adminconsent") and "client_id=app-1" in link


def test_graph_assertion_assinada_com_certificado():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    ass = grmod.assertion_certificado("tenant-1", "app-1", pem, "AABBCC", agora=1_000)
    cab = jwt.get_unverified_header(ass)
    corpo = jwt.decode(ass, chave.public_key(), algorithms=["RS256"], audience="https://login.microsoftonline.com/tenant-1/oauth2/v2.0/token",
                       options={"verify_exp": False})
    assert cab["x5t"] == "AABBCC" and corpo["iss"] == "app-1" and corpo["sub"] == "app-1"


# ---- Google ----
def test_google_historico_incremental():
    srv = Servidor({"/history": {"history": [{"messagesAdded": [{"message": {"id": "m1"}}]}], "historyId": "200"},
                    "/messages/m1": {"id": "m1", "snippet": "oi", "internalDate": "1760004000000",
                                     "payload": {"headers": [{"name": "Message-ID", "value": "<g1>"}, {"name": "From", "value": "a@x.com"}, {"name": "Subject", "value": "Oi"}]}}})
    g = Google(token=lambda: "tk", http=srv)
    msgs, hid = g.historico_gmail("a@x.com", "100")
    assert "startHistoryId=100" in srv.chamadas[0][1] and hid == "200"
    assert msgs[0]["message_id"] == "<g1>" and msgs[0]["remetente"] == "a@x.com" and msgs[0]["trecho"] == "oi"


def test_google_historico_expirado_faz_resync_completo_uma_vez():
    srv = Servidor({"/history": [(404, {"error": {"message": "notFound"}})],
                    "/messages?": {"messages": [{"id": "m1"}]},
                    "/messages/m1": {"id": "m1", "snippet": "", "internalDate": "1760004000000", "payload": {"headers": []}},
                    "/profile": {"historyId": "300"}})
    msgs, hid = Google(token=lambda: "tk", http=srv).historico_gmail("a@x.com", "1")
    assert hid == "300" and len(msgs) == 1
    assert sum("/history" in c[1] for c in srv.chamadas) == 1     # não insiste em loop


def test_google_criar_rascunho_nunca_envia():
    srv = Servidor({"/drafts": {"id": "d1"}})
    assert Google(token=lambda: "tk", http=srv).criar_rascunho("a@x.com", ["b@x.com"], "A", "C") == "d1"
    assert all("send" not in c[1].lower() for c in srv.chamadas)
    assert not [n for n in dir(Google) if "send" in n.lower() or "enviar" in n.lower() or n.lstrip("_").startswith(("delete", "apagar"))]


def test_google_servico_assina_jwt_com_delegacao():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    ass = gmod.assertion_servico("sa@p.iam", pem.decode(), "ricardo@bekaa.eu", ["https://www.googleapis.com/auth/gmail.readonly"], agora=1_000)
    c = jwt.decode(ass, chave.public_key(), algorithms=["RS256"], audience="https://oauth2.googleapis.com/token", options={"verify_exp": False})
    assert c["iss"] == "sa@p.iam" and c["sub"] == "ricardo@bekaa.eu"


def test_dedupe_por_message_id_entre_google_e_graph(tmp_path):
    from pathlib import Path
    from gabi.db import conectar, migrar
    from gabi.trabalho import email
    con = conectar(tmp_path / "g.db")
    migrar(con, Path(__file__).parent.parent.parent / "migrations")
    con.execute("insert into caixa_email(id, endereco, provedor, estado) values (1,'n@ness','google','sim')")
    con.execute("insert into caixa_email(id, endereco, provedor, estado) values (2,'n@ness','graph','sim')".replace("n@ness", "n@ness.com"))
    msg = {"message_id": "<mesmo>", "remetente": "a@x.com", "assunto": "Oi", "recebido_em": "2026-10-09T10:00:00Z", "trecho": "oi"}
    email.ingerir_email(con, 1, lambda c, cur: ([msg], "h"))
    email.ingerir_email(con, 2, lambda c, cur: ([msg], "d"))
    assert con.execute("select count(*) from item_email").fetchone()[0] == 1
