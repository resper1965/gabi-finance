"""Gmail para o correio do brain: LEITURA e LIXEIRA (mover e restaurar). Só o serviço `gabi-brain-fontes` tem rede e segredos (R5); o resto
do brain chega aqui pela ponte (`PonteEmail`). O refresh token da conta é o mesmo mecanismo de contatos e agenda (`google_oauth.TokenOAuth`).

TRAVA NO CÓDIGO: o menor escopo do Gmail que move para a lixeira é `gmail.modify`, que também permitiria enviar e apagar de vez. A garantia
de que isso nunca acontece é este módulo: só `GET` (mensagens, histórico, perfil), mais `POST` em `.../trash` e `.../untrash` (e o POST do
token em `google_oauth`). Não existe método de enviar, rascunho, apagar de vez nem rótulo livre; um teste varre o código e o `http` falso
recusa qualquer outra chamada. Não guarda corpo completo: só cabeçalhos úteis e o `snippet` curto. Segredo e corpo de resposta nunca entram em
erro, log ou repr. Docs: docs/fontes/google.md."""
import datetime as dt
import html
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from email.utils import parseaddr
from typing import Callable

from gabi.fontes.google_oauth import (ErroGoogleOAuth, TokenOAuth, _http_real, chamar, conta_valida, credenciais_do_ambiente)

ESCOPO = "https://www.googleapis.com/auth/gmail.modify"
BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_PAGINAS = 50
MAX_CARGA_MSGS = 200      # a ponte espera 130 s por chamada: uma carga lê no máximo as 200 mais recentes da janela (1 GET por mensagem)
MAX_ENVIADOS_MSGS = 200   # só os enviados mais recentes entram na lista de "já respondi" (o resto é conferido ao vivo por `respondeu_a`)
MAX_ENDERECOS_CONSULTA = 20
MAX_ENDERECOS = 5000
MAX_IDS_POR_CHAMADA = 100
TAM_TRECHO = 280
TAM_ASSUNTO = 300
_ID = re.compile(r"^[0-9a-f]{6,32}$")
_ENDERECO = re.compile(r"^[a-z0-9._%+'-]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,}$")
_CABECALHOS = ("From", "Subject", "List-Unsubscribe", "Precedence", "Auto-Submitted")
_FORA = {"TRASH", "SPAM", "DRAFT", "SENT"}


@dataclass
class ResultadoEmail:
    mensagens: list[dict] = field(default_factory=list)
    novo_history_id: str | None = None
    recarga_completa: bool = False


def _pegar(http, token, conta: str, metodo: str, url: str):
    """Requisição com o token da conta; um 401 invalida o access token em cache e repete UMA vez com token novo."""
    corpo = {} if metodo == "POST" else None
    cab = {"Authorization": f"Bearer {token(conta)}"}
    status, resp = chamar(http, metodo, url, corpo, cab)
    if status == 401 and hasattr(token, "invalidar"):
        token.invalidar(conta)
        status, resp = chamar(http, metodo, url, corpo, {"Authorization": f"Bearer {token(conta)}"})
    return status, resp


def _endereco(valor) -> str:
    if not isinstance(valor, str):
        return ""
    a = parseaddr(valor)[1].strip().lower()
    return a if _ENDERECO.match(a) else ""


def _cabecalhos(msg: dict) -> dict:
    saida = {}
    for h in (msg.get("payload") or {}).get("headers") or []:
        if isinstance(h, dict) and isinstance(h.get("name"), str) and isinstance(h.get("value"), str):
            saida.setdefault(h["name"].lower(), h["value"])
    return saida


def _lista(cab: dict) -> bool:
    """Sinal de e-mail de lista/automático: `List-Unsubscribe`, `Precedence: bulk|list|junk` ou `Auto-Submitted` diferente de `no`."""
    if "list-unsubscribe" in cab:
        return True
    if cab.get("precedence", "").strip().lower() in ("bulk", "list", "junk"):
        return True
    auto = cab.get("auto-submitted")
    return auto is not None and auto.strip().lower() != "no"


def _mensagem(msg: dict) -> dict | None:
    """None se não é da caixa de entrada (lixeira, spam, rascunho, enviado) ou se vem malformada."""
    if not isinstance(msg, dict) or not isinstance(msg.get("id"), str) or not _ID.match(msg["id"]):
        return None
    rotulos = msg.get("labelIds") or []
    if "INBOX" not in rotulos or _FORA & set(rotulos):
        return None
    try:
        recebida = dt.datetime.fromtimestamp(int(msg["internalDate"]) / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    cab = _cabecalhos(msg)
    snippet = msg.get("snippet")
    return {"externo_id": msg["id"], "thread_id": msg["threadId"] if isinstance(msg.get("threadId"), str) else msg["id"],
            "remetente": _endereco(cab.get("from")), "assunto": cab.get("subject", "")[:TAM_ASSUNTO],
            "recebida_em": recebida, "trecho": html.unescape(snippet)[:TAM_TRECHO] if isinstance(snippet, str) else "", "lista": _lista(cab)}


_VENENO = (400, 410, 413, 422)  # 4xx que é do id (e não da credencial, cota ou servidor: 401/403/429/5xx continuam parando a leitura)
_ACOES_MOVER = ("trash", "untrash")


def _metadados(conta, ids, token, http, cabecalhos=_CABECALHOS) -> list[dict]:
    saida = []
    q = "&".join("metadataHeaders=" + urllib.parse.quote(h) for h in cabecalhos)
    for i in ids:
        status, resp = _pegar(http, token, conta, "GET", f"{BASE}/messages/{i}?format=metadata&{q}")
        if status == 404 or status in _VENENO:
            continue  # apagada entre a listagem e a leitura; ou "veneno" (4xx persistente só naquele id): pula, não trava a conta
        if status >= 400:
            raise ErroGoogleOAuth(f"messages.get -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleOAuth("resposta inválida do Google")
        saida.append(resp)
    return saida


def _ids_paginados(conta, url_base: str, campo: str, token, http, maximo: int | None = None) -> tuple[list[str], dict]:
    """Todas as páginas (teto de MAX_PAGINAS; página repetida ou sem fim é erro, nunca lista parcial). Devolve (ids, última página)."""
    ids, pagina, vistas, ultima = [], None, set(), {}
    for _ in range(MAX_PAGINAS):
        url = url_base + (f"&pageToken={urllib.parse.quote(pagina)}" if pagina else "")
        status, resp = _pegar(http, token, conta, "GET", url)
        if status == 404:
            raise _HistoricoExpirado()
        if status >= 400:
            raise ErroGoogleOAuth(f"{campo} -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleOAuth("resposta inválida do Google")
        ultima = resp
        for item in resp.get(campo) or []:
            if campo == "messages":
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    ids.append(item["id"])
            else:  # history: [{messagesAdded: [{message: {id}}]}]
                for add in (item.get("messagesAdded") or []) if isinstance(item, dict) else []:
                    m = add.get("message") if isinstance(add, dict) else None
                    if isinstance(m, dict) and isinstance(m.get("id"), str):
                        ids.append(m["id"])
        if maximo is not None and len(ids) >= maximo:
            return ids[:maximo], resp
        pagina = resp.get("nextPageToken")
        if not pagina:
            return ids, ultima
        if pagina in vistas:
            break
        vistas.add(pagina)
    raise ErroGoogleOAuth("paginação sem fim")


class _HistoricoExpirado(Exception):
    pass


def _carga(conta, janela_dias: int, token, http) -> ResultadoEmail:
    """Primeira carga ou recarga: o historyId do perfil é lido ANTES da listagem (o que chegar no meio entra na próxima incremental)."""
    status, perfil = _pegar(http, token, conta, "GET", f"{BASE}/profile")
    if status >= 400 or not isinstance(perfil, dict):
        raise ErroGoogleOAuth(f"profile -> {status}")
    hid = perfil.get("historyId")
    q = urllib.parse.quote(f"in:inbox newer_than:{int(janela_dias)}d")
    try:
        ids, _ = _ids_paginados(conta, f"{BASE}/messages?q={q}&maxResults=100", "messages", token, http, maximo=MAX_CARGA_MSGS)
    except _HistoricoExpirado:
        raise ErroGoogleOAuth("messages.list -> 404") from None
    msgs = [m for m in (_mensagem(x) for x in _metadados(conta, ids, token, http)) if m]
    return ResultadoEmail(msgs, str(hid) if hid is not None else None, False)


def listar_novos(conta: str, history_id: str | None, janela_dias: int, token: Callable[[str], str], http=_http_real) -> ResultadoEmail:
    """Mensagens novas na caixa de entrada. Sem `history_id`: carga pela janela. Com ele: só o que chegou (`history.list`); 404 (histórico expirado) →
    recarga da janela (`recarga_completa=True`). Nunca devolve lista parcial."""
    conta = conta_valida(conta)
    if not isinstance(janela_dias, int) or isinstance(janela_dias, bool) or not 1 <= janela_dias <= 365:
        raise ErroGoogleOAuth("janela inválida")
    if history_id is None:
        return _carga(conta, janela_dias, token, http)
    if not isinstance(history_id, str) or not history_id.isdigit():
        raise ErroGoogleOAuth("historyId inválido")
    url = f"{BASE}/history?startHistoryId={history_id}&historyTypes=messageAdded&labelId=INBOX&maxResults=500"
    try:
        ids, ultima = _ids_paginados(conta, url, "history", token, http)
    except _HistoricoExpirado:
        r = _carga(conta, janela_dias, token, http)
        r.recarga_completa = True
        return r
    novo = ultima.get("historyId")
    unicos = list(dict.fromkeys(ids))
    if len(unicos) > MAX_CARGA_MSGS:  # chegou muita coisa de uma vez: lê só as mais recentes da janela (cabe no tempo da ponte) e avisa que recarregou
        r = _carga(conta, janela_dias, token, http)
        r.recarga_completa = True
        return r
    msgs = [m for m in (_mensagem(x) for x in _metadados(conta, unicos, token, http)) if m]
    return ResultadoEmail(msgs, str(novo) if novo is not None else history_id, False)


def _mover(conta: str, ids, acao: str, token, http) -> dict[str, str]:
    if acao not in _ACOES_MOVER:  # as únicas escritas que o cliente faz; qualquer outra ação é recusada antes de chamar o Google
        raise ErroGoogleOAuth("ação não permitida")
    conta = conta_valida(conta)
    if not isinstance(ids, (list, tuple)) or len(ids) > MAX_IDS_POR_CHAMADA:
        raise ErroGoogleOAuth(f"no máximo {MAX_IDS_POR_CHAMADA} ids por chamada")
    resultado = {}
    for i in ids:
        if not isinstance(i, str) or not _ID.match(i):
            raise ErroGoogleOAuth("id de mensagem inválido")
        try:
            status, _ = _pegar(http, token, conta, "POST", f"{BASE}/messages/{i}/{acao}")
            resultado[i] = "ok" if status < 400 else "erro"
        except ErroGoogleOAuth:
            resultado[i] = "erro"  # falha de um id não aborta o lote
    return resultado


def lixeira(conta: str, ids, token: Callable[[str], str], http=_http_real) -> dict[str, str]:
    """Move para a lixeira (o Gmail a esvazia em 30 dias). Por id: `ok` ou `erro`; a falha de um não aborta os outros."""
    return _mover(conta, ids, "trash", token, http)


def restaurar(conta: str, ids, token: Callable[[str], str], http=_http_real) -> dict[str, str]:
    """Tira da lixeira. Idempotente (restaurar o que já está fora da lixeira é `ok`)."""
    return _mover(conta, ids, "untrash", token, http)


def enviados_recentes(conta: str, dias: int, token: Callable[[str], str], http=_http_real) -> list[str]:
    """Endereços de To/Cc dos e-mails que o dono enviou (os MAX_ENVIADOS_MSGS mais recentes na janela), minúsculos e sem repetir."""
    conta = conta_valida(conta)
    if not isinstance(dias, int) or isinstance(dias, bool) or not 1 <= dias <= 3650:
        raise ErroGoogleOAuth("janela inválida")
    q = urllib.parse.quote(f"in:sent newer_than:{dias}d")
    try:
        ids, _ = _ids_paginados(conta, f"{BASE}/messages?q={q}&maxResults=100", "messages", token, http, maximo=MAX_ENVIADOS_MSGS)
    except _HistoricoExpirado:
        raise ErroGoogleOAuth("messages.list -> 404") from None
    vistos: dict[str, None] = {}
    for msg in _metadados(conta, ids, token, http, cabecalhos=("To", "Cc")):
        cab = _cabecalhos(msg)
        for campo in ("to", "cc"):
            for parte in re.split(r"[,;]", cab.get(campo, "")):
                a = _endereco(parte)
                if a:
                    vistos.setdefault(a)
    return list(vistos)[:MAX_ENDERECOS]


def respondeu_a(conta: str, enderecos, token: Callable[[str], str], http=_http_real) -> dict[str, bool]:
    """O dono já escreveu (To, Cc ou Bcc) para cada endereço? Consulta exata ao Gmail (`in:sent to:<endereço>`), sem o limite da lista dos enviados
    recentes. Erro do Gmail é erro tipado: quem chama trata como "não confirmado" (na dúvida o e-mail fica na caixa), nunca como "não respondeu"."""
    conta = conta_valida(conta)
    if not isinstance(enderecos, (list, tuple)) or not 1 <= len(enderecos) <= MAX_ENDERECOS_CONSULTA:
        raise ErroGoogleOAuth(f"de 1 a {MAX_ENDERECOS_CONSULTA} endereços por chamada")
    normais = []
    for e in enderecos:
        a = _endereco(e) if isinstance(e, str) and e.strip().lower() == _endereco(e) else ""
        if not a:
            raise ErroGoogleOAuth("endereço inválido")
        normais.append(a)
    saida = {}
    for a in normais:
        q = urllib.parse.quote(f"in:sent to:{a}")
        status, resp = _pegar(http, token, conta, "GET", f"{BASE}/messages?q={q}&maxResults=1")
        if status >= 400 or not isinstance(resp, dict):
            raise ErroGoogleOAuth(f"messages.list -> {status}")
        saida[a] = bool(resp.get("messages"))
    return saida


class GoogleEmail:
    """Objeto da ponte (JSON puro). Sem o token provider nada sai."""

    def __init__(self, token: Callable[[str], str], http=_http_real):
        self._token, self._http = token, http

    def __repr__(self):
        return "GoogleEmail(<oculto>)"

    def listar_novos(self, conta: str, history_id: str | None, janela_dias: int) -> dict:
        return asdict(listar_novos(conta, history_id, janela_dias, self._token, self._http))

    def lixeira(self, conta: str, ids) -> dict:
        return lixeira(conta, ids, self._token, self._http)

    def restaurar(self, conta: str, ids) -> dict:
        return restaurar(conta, ids, self._token, self._http)

    def enviados_recentes(self, conta: str, dias: int) -> list[str]:
        return enviados_recentes(conta, dias, self._token, self._http)

    def respondeu_a(self, conta: str, enderecos) -> dict:
        return respondeu_a(conta, enderecos, self._token, self._http)


def google_email_do_ambiente(env) -> GoogleEmail | None:
    """None ("não configurada") sem o cliente OAuth do Google no ambiente do serviço."""
    cred = credenciais_do_ambiente(env)
    if cred is None:
        return None
    return GoogleEmail(TokenOAuth(cred[0], cred[1], env))
