"""Cliente Microsoft Graph (IONIC; ness depois da migração). Docs: docs/fontes/graph.md.

R2: só LÊ e cria RASCUNHO (nunca envia, nunca apaga). R5: o token vem de um callable de quem instancia; nada de credencial aqui.
Autenticação do app por certificado: `assertion_certificado` monta o JWT; trocar por token é de quem monta o `token`. Consome: nada."""
import time
import uuid
from typing import Callable
from urllib.parse import quote

import jwt

from gabi.fontes._http import http_real

BASE = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"


class ErroGraph(Exception):
    pass


def link_aprovacao_admin(tenant: str, client_id: str) -> str:
    """Link para o administrador do tenant aprovar o app (G11): o Ricardo só copia e envia."""
    return f"{LOGIN}/{quote(tenant)}/adminconsent?client_id={quote(client_id)}"


def assertion_certificado(tenant: str, client_id: str, chave_pem: bytes, x5t: str, agora: int | None = None) -> str:
    """JWT de client_assertion (RS256, thumbprint em x5t) para o fluxo client_credentials com certificado."""
    t = int(agora if agora is not None else time.time())
    return jwt.encode({"aud": f"{LOGIN}/{tenant}/oauth2/v2.0/token", "iss": client_id, "sub": client_id, "jti": str(uuid.uuid4()),
                       "nbf": t, "exp": t + 600}, chave_pem, algorithm="RS256", headers={"x5t": x5t})


class Graph:
    def __init__(self, token: Callable[[], str], base: str = BASE, *, http=None):
        self._token, self.base, self._http = token, base.rstrip("/"), http or http_real

    def _req(self, metodo: str, url: str, corpo=None):
        status, resp = self._http(metodo, url, corpo, {"Authorization": f"Bearer {self._token()}"})
        if status >= 400:
            msg = (resp or {}).get("error", {}).get("message", "") if isinstance(resp, dict) else ""
            raise ErroGraph(f"{metodo} {url.split('?')[0]} -> {status}" + (f": {msg}" if msg else ""))
        return resp

    def _delta(self, url: str) -> tuple[list[dict], str]:
        itens = []
        while True:
            r = self._req("GET", url)
            itens += r.get("value", [])
            if "@odata.nextLink" in r:
                url = r["@odata.nextLink"]
            else:
                return itens, r["@odata.deltaLink"]

    def delta_mensagens(self, caixa: str, token_delta: str | None) -> tuple[list[dict], str]:
        """Só o que mudou desde `token_delta` (o deltaLink devolvido na rodada anterior). Formato igual ao de `trabalho.email.ingerir_email`."""
        url = token_delta or f"{self.base}/users/{quote(caixa)}/mailFolders/inbox/messages/delta"
        itens, novo = self._delta(url)
        return [{"message_id": i["internetMessageId"], "remetente": i.get("from", {}).get("emailAddress", {}).get("address", ""),
                 "assunto": i.get("subject"), "recebido_em": i["receivedDateTime"], "trecho": i.get("bodyPreview", "")}
                for i in itens if "internetMessageId" in i], novo

    def delta_eventos(self, caixa: str, token_delta: str | None) -> tuple[list[dict], str]:
        url = token_delta or f"{self.base}/users/{quote(caixa)}/calendarView/delta"
        itens, novo = self._delta(url)
        return [{"externo_id": i["id"], "inicio": i["start"]["dateTime"], "fim": i["end"]["dateTime"], "titulo": i.get("subject"),
                 "participantes": [a["emailAddress"]["address"] for a in i.get("attendees", [])],
                 "link_reuniao": (i.get("onlineMeeting") or {}).get("joinUrl")} for i in itens if "start" in i], novo

    def tarefas(self, caixa: str) -> list[dict]:
        r = self._req("GET", f"{self.base}/users/{quote(caixa)}/todo/lists")
        saida = []
        for lista in r.get("value", []):
            ts = self._req("GET", f"{self.base}/users/{quote(caixa)}/todo/lists/{lista['id']}/tasks")
            saida += [{"externo_id": t["id"], "titulo": t["title"], "prazo": (t.get("dueDateTime") or {}).get("dateTime"),
                       "concluida": t.get("status") == "completed"} for t in ts.get("value", [])]
        return saida

    def criar_rascunho(self, caixa: str, para: list[str], assunto: str, corpo: str) -> str:
        """Cria rascunho na caixa (fica em Rascunhos). Não há envio nesta classe."""
        r = self._req("POST", f"{self.base}/users/{quote(caixa)}/messages",
                      {"subject": assunto, "body": {"contentType": "Text", "content": corpo},
                       "toRecipients": [{"emailAddress": {"address": a}} for a in para]})
        return r["id"]
