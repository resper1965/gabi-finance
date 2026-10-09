"""Cliente Google (Gmail, Agenda, Tasks) das 4 contas: conta de serviço com delegação (bekaa.eu, esper.ws) ou OAuth próprio (ness, Gmail).
Docs: docs/fontes/google.md. R2: só lê e cria RASCUNHO (sem envio, sem exclusão). R5: o token vem de um callable; refresh tokens ficam no arquivo de ambiente."""
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote

import jwt

from gabi.fontes._http import http_real

GMAIL = "https://gmail.googleapis.com/gmail/v1/users"
AGENDA = "https://www.googleapis.com/calendar/v3"
TASKS = "https://tasks.googleapis.com/tasks/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"
RESYNC_MAX = 200


class ErroGoogle(Exception):
    pass


def assertion_servico(email_sa: str, chave_pem: str, usuario: str, escopos: list[str], agora: int | None = None) -> str:
    """JWT da conta de serviço com delegação (`sub` = a caixa que ela representa)."""
    t = int(agora if agora is not None else time.time())
    return jwt.encode({"iss": email_sa, "sub": usuario, "scope": " ".join(escopos), "aud": TOKEN_URL, "iat": t, "exp": t + 3000},
                      chave_pem, algorithm="RS256")


class Google:
    def __init__(self, token: Callable[[], str], *, http=None):
        self._token, self._http = token, http or http_real

    def _req(self, metodo: str, url: str, corpo=None, tolerar_404: bool = False):
        status, resp = self._http(metodo, url, corpo, {"Authorization": f"Bearer {self._token()}"})
        if status == 404 and tolerar_404:
            return None
        if status >= 400:
            msg = (resp or {}).get("error", {}).get("message", "") if isinstance(resp, dict) else ""
            raise ErroGoogle(f"{metodo} {url.split('?')[0]} -> {status}" + (f": {msg}" if msg else ""))
        return resp

    def _mensagem(self, caixa: str, mid: str) -> dict:
        m = self._req("GET", f"{GMAIL}/{quote(caixa)}/messages/{mid}?format=metadata&metadataHeaders=Message-ID&metadataHeaders=From&metadataHeaders=Subject")
        h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        recebido = datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"message_id": h.get("message-id") or f"gmail:{m['id']}", "remetente": h.get("from", ""), "assunto": h.get("subject"),
                "recebido_em": recebido, "trecho": m.get("snippet", "")}

    def historico_gmail(self, caixa: str, start_history_id: str | None) -> tuple[list[dict], str]:
        """Incremental por historyId. Se o histórico expirou (404), faz UM resync completo das mensagens recentes e segue."""
        if start_history_id:
            r = self._req("GET", f"{GMAIL}/{quote(caixa)}/history?startHistoryId={start_history_id}&historyTypes=messageAdded", tolerar_404=True)
            if r is not None:
                ids = [a["message"]["id"] for h in r.get("history", []) for a in h.get("messagesAdded", [])]
                return [self._mensagem(caixa, i) for i in dict.fromkeys(ids)], r.get("historyId", start_history_id)
        lista = self._req("GET", f"{GMAIL}/{quote(caixa)}/messages?maxResults={RESYNC_MAX}")
        perfil = self._req("GET", f"{GMAIL}/{quote(caixa)}/profile")
        return [self._mensagem(caixa, m["id"]) for m in lista.get("messages", [])], perfil["historyId"]

    def eventos(self, caixa: str, sync_token: str | None) -> tuple[list[dict], str | None]:
        url = f"{AGENDA}/calendars/{quote(caixa)}/events?singleEvents=true" + (f"&syncToken={quote(sync_token)}" if sync_token else "")
        r = self._req("GET", url)
        return [{"externo_id": e["id"], "inicio": e["start"].get("dateTime", e["start"].get("date")), "fim": e["end"].get("dateTime", e["end"].get("date")),
                 "titulo": e.get("summary"), "participantes": [a["email"] for a in e.get("attendees", [])], "link_reuniao": e.get("hangoutLink")}
                for e in r.get("items", []) if e.get("status") != "cancelled"], r.get("nextSyncToken")

    def tasks(self, caixa: str) -> list[dict]:
        saida = []
        for lista in self._req("GET", f"{TASKS}/users/@me/lists").get("items", []):
            for t in self._req("GET", f"{TASKS}/lists/{lista['id']}/tasks").get("items", []):
                saida.append({"externo_id": f"{lista['id']}/{t['id']}", "titulo": t.get("title", ""), "prazo": t.get("due"), "concluida": t.get("status") == "completed"})
        return saida

    def criar_rascunho(self, caixa: str, para: list[str], assunto: str, corpo: str) -> str:
        import base64
        from email.message import EmailMessage
        msg = EmailMessage()  # cabeçalhos com acento saem codificados (RFC 2047)
        msg["To"], msg["Subject"] = ", ".join(para), assunto
        msg.set_content(corpo)
        bruto = msg.as_bytes().decode("ascii", "replace")
        r = self._req("POST", f"{GMAIL}/{quote(caixa)}/drafts", {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}})
        return r["id"]

    def concluir_tarefa(self, externo_id: str) -> None:
        """Marca a tarefa como concluída no Google Tasks (`externo_id` = lista/tarefa; PATCH do status; sem exclusão)."""
        lista_id, tarefa_id = externo_id.split("/", 1)
        self._req("PATCH", f"{TASKS}/lists/{lista_id}/tasks/{tarefa_id}", {"status": "completed"})
