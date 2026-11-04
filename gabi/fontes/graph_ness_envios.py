"""Envios aprovados no Graph da ness (ADR-024): CRIAR EVENTO na agenda e RESPONDER A CONVITE recebido (accept, tentativelyAccept, decline;
token de aplicativo, `Calendars.ReadWrite`; o Exchange manda os convites e as respostas) e, com token DELEGADO do Ricardo, listar equipes e canais
do Teams, escrever em chat que já existe e postar em canal. Nada mais: não cria chat, não manda e-mail, não responde e-mail nem encaminha, não
altera nem apaga (uma varredura fixa os verbos e as URLs deste arquivo). Fica fora de
`graph_ness.py` para que a trava de leitura daquele arquivo continue valendo. O texto do Teams sai como `contentType: text`, intacto (nunca HTML).
O refresh token delegado vem de GRAPH_NESS_TEAMS_REFRESH; o novo que a Microsoft devolve fica só em memória. Título, texto, nomes, e-mails,
token e corpo de resposta nunca entram em erro, log ou repr: erros são códigos fixos ou `operacao -> status`.
Consome: graph_ness (BASE, LOGIN, FOLGA_S, ErroGraphNess, _ErroStatus, _chamar, _http_real; a conta e o token de app vêm do `GraphNess`)."""
import json
import re
import time
import urllib.parse

from gabi.fontes.graph_ness import _CHAT_ID, BASE, FOLGA_S, HOST, LOGIN, ErroGraphNess, _chamar, _ErroStatus, _http_real

ESCOPO_TEAMS = ("https://graph.microsoft.com/ChatMessage.Send https://graph.microsoft.com/ChannelMessage.Send "
                "https://graph.microsoft.com/Team.ReadBasic.All https://graph.microsoft.com/Channel.ReadBasic.All offline_access")
_CHAVE = re.compile(r"^[0-9a-v]{26}$")  # chave da proposta: 26 caracteres base32hex minúsculos (vira `transactionId`)
_ID_TEAMS = re.compile(r"^[0-9A-Za-z:@._-]{1,200}$")  # id de equipe (GUID) ou de canal ("19:...@thread.tacv2"): nunca "/" nem espaço
_ID_EVENTO = re.compile(r"^[A-Za-z0-9_=+/-]{1,300}$")  # id de evento do Graph (base64): vai ao caminho sempre por quote(safe="")
_ACAO_CONVITE = {"aceitar": "accept", "talvez": "tentativelyAccept", "recusar": "decline"}
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MAX_TEXTO = 4000
MAX_PAGINAS = 20


class TokenDelegado:
    """token() -> access token delegado (Teams) da conta `conta_esperada`, por refresh token de cliente público (sem secret). Guarda em memória
    até FOLGA_S antes de expirar. Na primeira troca confere pelo `/me` que o login é da conta esperada."""

    def __init__(self, tenant: str, client_id: str, refresh: str, conta_esperada: str, http=_http_real, agora=time.time):
        self._tenant, self._id, self._refresh, self._http, self._agora = tenant, client_id, refresh, http, agora
        self.conta = conta_esperada.strip().lower()
        self._cache: tuple[str, float] | None = None
        self._conferido = False

    def __repr__(self):
        return "TokenDelegado(<oculto>)"

    def __call__(self) -> str:
        if self._cache and self._agora() < self._cache[1]:
            return self._cache[0]
        corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": self._id, "refresh_token": self._refresh,
                                        "scope": ESCOPO_TEAMS}).encode()
        url = f"{LOGIN}/{urllib.parse.quote(self._tenant, safe='')}/oauth2/v2.0/token"
        status, resp = _chamar(self._http, "POST", url, corpo, {"Content-Type": "application/x-www-form-urlencoded"})
        if status in (400, 401):
            raise ErroGraphNess("login_teams_expirado")
        if status >= 300:
            raise ErroGraphNess(f"troca de token teams -> {status}")
        acc = resp.get("access_token") if isinstance(resp, dict) else None
        exp = resp.get("expires_in") if isinstance(resp, dict) else None
        if not isinstance(acc, str) or not acc or isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise ErroGraphNess("resposta inválida na troca de token teams")
        novo = resp.get("refresh_token")
        if isinstance(novo, str) and novo:
            self._refresh = novo  # rotacionado: só em memória (depois de um reinício vale o do ambiente)
        if not self._conferido:
            self._conferir(acc)
        self._cache = (acc, self._agora() + exp - FOLGA_S)
        return acc

    def _conferir(self, acc: str) -> None:
        status, resp = _chamar(self._http, "GET", f"{BASE}/me?$select=userPrincipalName", None, {"Authorization": f"Bearer {acc}"})
        if status >= 300:
            raise ErroGraphNess(f"GET /me -> {status}")
        upn = resp.get("userPrincipalName") if isinstance(resp, dict) else None
        if not isinstance(upn, str) or upn.strip().lower() != self.conta:
            raise ErroGraphNess("login_teams_conta_diferente")
        self._conferido = True

    def invalidar(self) -> None:
        self._cache = None


def _conta(fonte, conta) -> str:
    if not isinstance(conta, str) or conta.strip().lower() not in fonte.contas():
        raise ErroGraphNess("conta não autorizada")
    return conta.strip().lower()


def _delegado(fonte, conta):
    """Token delegado da conta; sem login do Teams no ambiente, `teams_sem_login`."""
    conta = _conta(fonte, conta)
    token = getattr(fonte, "_token_teams", None)
    if token is None:
        raise ErroGraphNess("teams_sem_login")
    if getattr(token, "conta", None) != conta:
        raise ErroGraphNess("login_teams_conta_diferente")
    return token


def _id(v, erro: str) -> str:
    if not isinstance(v, str) or not _ID_TEAMS.match(v):
        raise ErroGraphNess(erro)
    return urllib.parse.quote(v, safe="")


def _texto(v) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > MAX_TEXTO:
        raise ErroGraphNess("texto inválido")
    return v


def _pedir(fonte, token, metodo: str, url: str, corpo: dict | None, operacao: str) -> dict:
    """Chamada autenticada só ao host do Graph; um 401 invalida o token e repete UMA vez. Status >= 300 vira `operacao -> status`, sem corpo.
    Exige corpo JSON objeto na resposta (a resposta a convite, que volta 202 vazia, usa `_pedir_vazio`)."""
    resp = _pedir_vazio(fonte, token, metodo, url, corpo, operacao)
    if not isinstance(resp, dict):
        raise ErroGraphNess("resposta inválida do Graph")
    return resp


def _pedir_vazio(fonte, token, metodo: str, url: str, corpo: dict | None, operacao: str):
    """Como `_pedir`, mas um 2xx vale com qualquer corpo (inclusive nenhum); devolve o que veio, sem conferir a forma."""
    if not url.startswith(HOST):
        raise ErroGraphNess("link inválido")
    dados = None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode()
    for tentativa in (1, 2):
        cab = {"Authorization": f"Bearer {token()}", **({} if dados is None else {"Content-Type": "application/json"})}
        status, resp = _chamar(fonte._http, metodo, url, dados, cab)
        if status == 401 and tentativa == 1 and hasattr(token, "invalidar"):
            token.invalidar()
            continue
        break
    if status >= 300:
        raise _ErroStatus(f"{operacao} -> {status}", status)
    return resp


def _externo(resp: dict) -> dict:
    novo = resp.get("id")
    if not isinstance(novo, str) or not novo:
        raise ErroGraphNess("resposta inválida do Graph")
    return {"externo_id": novo}


def _hora(v) -> str:
    if not isinstance(v, str) or not _UTC.match(v):
        raise ErroGraphNess("evento inválido")
    return v[:-1]  # sem o "Z": o fuso vai em timeZone


def evento_criar(fonte, conta, chave, evento) -> dict:
    """Cria o evento na agenda da conta com `transactionId` = chave (o Graph não duplica a mesma chave). Convidados required; `online` pede Teams."""
    conta = _conta(fonte, conta)
    if not isinstance(chave, str) or not _CHAVE.match(chave):
        raise ErroGraphNess("chave inválida")
    if not isinstance(evento, dict) or not isinstance(evento.get("titulo"), str) or not isinstance(evento.get("convidados"), list):
        raise ErroGraphNess("evento inválido")
    descricao = evento.get("descricao") or ""
    if not isinstance(descricao, str) or not all(isinstance(e, str) for e in evento["convidados"]):
        raise ErroGraphNess("evento inválido")
    corpo = {"subject": evento["titulo"], "body": {"contentType": "text", "content": descricao},
             "start": {"dateTime": _hora(evento.get("inicio_utc")), "timeZone": "UTC"},
             "end": {"dateTime": _hora(evento.get("fim_utc")), "timeZone": "UTC"},
             "attendees": [{"emailAddress": {"address": e}, "type": "required"} for e in evento["convidados"]],
             "transactionId": chave}
    if evento.get("online") is True:
        corpo["isOnlineMeeting"] = True
        corpo["onlineMeetingProvider"] = "teamsForBusiness"
    url = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/events"
    return _externo(_pedir(fonte, fonte._token, "POST", url, corpo, "evento_criar"))


def convite_responder(fonte, conta, evento_id, resposta, serie_id) -> dict:
    """Responde ao convite na agenda da conta (accept/tentativelyAccept/decline) com `sendResponse` e sem comentário; se o convite é de uma série,
    responde a série (`serie_id`). O Graph devolve 202 sem corpo. Devolve {"externo_id": id respondido}."""
    conta = _conta(fonte, conta)
    acao = _ACAO_CONVITE.get(resposta) if isinstance(resposta, str) else None
    alvo = serie_id or evento_id
    if acao is None or not isinstance(alvo, str) or not _ID_EVENTO.fullmatch(alvo):
        raise ErroGraphNess("evento inválido")
    url = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/events/{urllib.parse.quote(alvo, safe='')}/{acao}"
    _pedir_vazio(fonte, fonte._token, "POST", url, {"sendResponse": True}, "convite_responder")
    return {"externo_id": alvo}


def _lista(fonte, token, url: str, operacao: str) -> list[dict]:
    saida = []
    for _ in range(MAX_PAGINAS):
        resp = _pedir(fonte, token, "GET", url, None, operacao)
        for item in resp.get("value") or []:
            if (isinstance(item, dict) and isinstance(item.get("id"), str) and _ID_TEAMS.match(item["id"])
                    and isinstance(item.get("displayName"), str)):
                saida.append({"id": item["id"], "nome": item["displayName"]})
        url = resp.get("@odata.nextLink")
        if not isinstance(url, str):
            break
    return saida


def teams_equipes(fonte, conta) -> list[dict]:
    """[{id, nome}] das equipes de que a conta é membro."""
    token = _delegado(fonte, conta)
    return _lista(fonte, token, f"{BASE}/me/joinedTeams?$select=id,displayName", "teams_equipes")


def teams_canais(fonte, conta, equipe_id) -> list[dict]:
    """[{id, nome}] dos canais da equipe que a conta enxerga."""
    token = _delegado(fonte, conta)
    equipe = _id(equipe_id, "equipe inválida")
    return _lista(fonte, token, f"{BASE}/teams/{equipe}/channels?$select=id,displayName", "teams_canais")


def _mensagem(texto: str) -> dict:
    return {"body": {"contentType": "text", "content": texto}}


def teams_chat_enviar(fonte, conta, chat_id, texto) -> dict:
    """Escreve em chat que já existe (nunca cria chat)."""
    token = _delegado(fonte, conta)
    if not isinstance(chat_id, str) or not _CHAT_ID.match(chat_id):
        raise ErroGraphNess("chat inválido")
    url = f"{BASE}/chats/{urllib.parse.quote(chat_id, safe='')}/messages"
    return _externo(_pedir(fonte, token, "POST", url, _mensagem(_texto(texto)), "teams_chat_enviar"))


def teams_canal_enviar(fonte, conta, equipe_id, canal_id, texto) -> dict:
    """Posta mensagem nova (não resposta) em canal de equipe de que a conta é membro."""
    token = _delegado(fonte, conta)
    equipe, canal = _id(equipe_id, "equipe inválida"), _id(canal_id, "canal inválido")
    url = f"{BASE}/teams/{equipe}/channels/{canal}/messages"
    return _externo(_pedir(fonte, token, "POST", url, _mensagem(_texto(texto)), "teams_canal_enviar"))
