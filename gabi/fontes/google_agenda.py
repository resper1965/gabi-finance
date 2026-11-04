"""Google Agenda (Calendar API v3): leitura + criar evento aprovado (ADR-024). Só o serviço `gabi-brain-fontes` tem rede e segredos (R5); o resto do brain chega aqui pela
ponte (`PonteAgenda`). O refresh token da conta (escopos calendar.readonly e calendar.events) é o mesmo mecanismo de contatos (`google_oauth.TokenOAuth`).
Não extrai e-mail de participante nem local: só a contagem de participantes. `syncToken` e janela (`timeMin/timeMax`) não convivem na API do
Google: a carga inicial usa a janela, as incrementais usam só o token; 410 (token expirado) refaz a janela completa. Cancelado é devolvido
à parte para quem chama apagar. Criar evento: POST com `id` = chave de idempotência (409 = já existia); título, descrição e e-mails nunca entram em erro. Segredo e corpo
de resposta nunca entram em erro, log ou repr. Consome: google_oauth (token da conta). Docs: docs/fontes/google.md."""
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Callable

from gabi.fontes._http import com_retry
from gabi.fontes.google_oauth import (ErroGoogleOAuth, TokenOAuth, _http_real, chamar, conta_valida, credenciais_do_ambiente)

ESCOPO = "https://www.googleapis.com/auth/calendar.readonly"
BASE = "https://www.googleapis.com/calendar/v3"
MAX_PAGINAS = 50
_CHAVE = re.compile(r"^[0-9a-v]{5,1024}$")  # alfabeto base32hex que o Google aceita em `id` de evento
_CALENDARIO = re.compile(r"^[A-Za-z0-9._@%+-]{1,200}$")  # "primary" ou id (e-mail, ...@group.calendar.google.com): nunca "/" nem espaço


@dataclass
class ResultadoEventos:
    eventos: list[dict] = field(default_factory=list)
    cancelados: list[str] = field(default_factory=list)
    novo_sync_token: str | None = None
    recarga_completa: bool = False


def _pegar(http, token, conta: str, url: str):
    """GET com o token da conta; um 401 invalida o access token em cache e repete UMA vez com token novo."""
    def uma():
        return com_retry(lambda: chamar(http, "GET", url, None, {"Authorization": f"Bearer {token(conta)}"}))
    status, resp = uma()
    if status == 401 and hasattr(token, "invalidar"):
        token.invalidar(conta)
        status, resp = uma()
    return status, resp


def _postar(http, token, conta: str, url: str, corpo: dict):
    """POST JSON com o token da conta; um 401 invalida o access token em cache e repete UMA vez com token novo."""
    def uma_vez():
        return chamar(http, "POST", url, corpo, {"Authorization": f"Bearer {token(conta)}", "Content-Type": "application/json"})
    status, resp = uma_vez()
    if status == 401 and hasattr(token, "invalidar"):
        token.invalidar(conta)
        status, resp = uma_vez()
    return status, resp


def evento_criar(conta: str, chave: str, evento: dict, token: Callable[[str], str], http=_http_real) -> dict:
    """Cria o evento no calendário principal com `id` = chave (idempotente: 409 -> ja_existia). Convida por e-mail (sendUpdates=all) e,
    se `online`, pede sala do Meet. Nada do conteúdo entra em mensagem de erro."""
    conta = conta_valida(conta)
    if not isinstance(chave, str) or not _CHAVE.match(chave):
        raise ErroGoogleOAuth("chave inválida")
    fuso = evento["fuso"]
    corpo = {"id": chave, "summary": evento["titulo"], "description": evento["descricao"],
             "start": {"dateTime": evento["inicio_utc"], "timeZone": fuso},
             "end": {"dateTime": evento["fim_utc"], "timeZone": fuso},
             "attendees": [{"email": e} for e in evento["convidados"]]}
    q = {"sendUpdates": "all"}
    if evento.get("online") is True:
        q["conferenceDataVersion"] = "1"
        corpo["conferenceData"] = {"createRequest": {"requestId": chave, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    status, _ = _postar(http, token, conta, f"{BASE}/calendars/primary/events?" + urllib.parse.urlencode(q), corpo)
    if status == 409:
        return {"externo_id": chave, "ja_existia": True}
    if status >= 400:
        raise ErroGoogleOAuth(f"calendar.events.insert -> {status}")
    return {"externo_id": chave, "ja_existia": False}


def listar_calendarios(conta: str, token: Callable[[str], str], http=_http_real) -> list[dict]:
    """[{id, nome, principal}] dos calendários que a conta enxerga (leitura ou mais)."""
    conta = conta_valida(conta)
    saida, pagina, vistas = [], None, set()
    for _ in range(MAX_PAGINAS):
        q = {"minAccessRole": "reader", "maxResults": "250"}
        if pagina:
            q["pageToken"] = pagina
        status, resp = _pegar(http, token, conta, f"{BASE}/users/me/calendarList?" + urllib.parse.urlencode(q))
        if status >= 400:
            raise ErroGoogleOAuth(f"calendarList.list -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleOAuth("resposta inválida do Google")
        for c in resp.get("items") or []:
            if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]:
                nome = c.get("summary")
                saida.append({"id": c["id"], "nome": nome if isinstance(nome, str) else None, "principal": c.get("primary") is True})
        pagina = resp.get("nextPageToken")
        if not pagina:
            return saida
        if pagina in vistas:
            break
        vistas.add(pagina)
    raise ErroGoogleOAuth("paginação sem fim")


def _link_reuniao(item: dict) -> str | None:
    """`hangoutLink` (Meet nativo) ou o primeiro ponto de entrada de vídeo de `conferenceData` (Zoom, Teams e outros add-ons). Só https; o local do
    evento nunca é lido."""
    hangout = item.get("hangoutLink")
    if isinstance(hangout, str) and hangout.startswith("https://"):
        return hangout
    conf = item.get("conferenceData")
    pontos = conf.get("entryPoints") if isinstance(conf, dict) else None
    for p in pontos if isinstance(pontos, list) else []:
        if isinstance(p, dict) and p.get("entryPointType") == "video" and isinstance(p.get("uri"), str) and p["uri"].startswith("https://"):
            return p["uri"]
    return None


def _evento(item: dict) -> dict:
    attendees = item.get("attendees")
    resumo = item.get("summary")
    return {"externo_id": item["id"], "inicio": item.get("start"), "fim": item.get("end"),
            "titulo": resumo if isinstance(resumo, str) else None,
            "link_reuniao": _link_reuniao(item),
            "participantes_qtd": len([a for a in attendees if isinstance(a, dict)]) if isinstance(attendees, list) else 0,
            "status": item.get("status") if isinstance(item.get("status"), str) else None,
            "etag": item.get("etag") if isinstance(item.get("etag"), str) else None,
            "atualizado_origem": item.get("updated") if isinstance(item.get("updated"), str) else None,
            "privado": item.get("visibility") in ("private", "confidential"),
            "ical_uid": item["iCalUID"] if isinstance(item.get("iCalUID"), str) and item["iCalUID"] else None,
            "livre": item.get("transparency") == "transparent"}


def _recusado_por_mim(item: dict) -> bool:
    """O próprio dono (`self`) recusou o convite. Só o campo de resposta é lido; e-mail de participante nunca é guardado."""
    return any(isinstance(a, dict) and a.get("self") is True and a.get("responseStatus") == "declined" for a in item.get("attendees") or [])


def _ler(conta, calendario_id, sync_token, janela, token, http):
    """Todas as páginas -> ResultadoEventos, ou None se o Google respondeu 410 (syncToken expirado) numa carga incremental."""
    base = f"{BASE}/calendars/{urllib.parse.quote(calendario_id, safe='')}/events"
    res, pagina, vistas = ResultadoEventos(), None, set()
    for _ in range(MAX_PAGINAS):
        q = {"singleEvents": "true", "maxResults": "2500"}
        if sync_token:
            q["syncToken"] = sync_token
        else:
            q["timeMin"], q["timeMax"] = janela["de"], janela["ate"]
        if pagina:
            q["pageToken"] = pagina
        status, resp = _pegar(http, token, conta, base + "?" + urllib.parse.urlencode(q))
        if status == 410 and sync_token:
            return None
        if status >= 400:
            raise ErroGoogleOAuth(f"calendar.events.list -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleOAuth("resposta inválida do Google")
        for item in resp.get("items") or []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                continue
            if item.get("status") == "cancelled" or _recusado_por_mim(item):
                res.cancelados.append(item["id"])  # recusado some do app do Google: some daqui (e apaga a linha já gravada)
            elif item.get("eventType") == "workingLocation":
                continue  # "Casa/Escritório" do dia não é compromisso
            else:
                res.eventos.append(_evento(item))
        pagina = resp.get("nextPageToken")
        if not pagina:
            res.novo_sync_token = resp.get("nextSyncToken") if isinstance(resp.get("nextSyncToken"), str) else None
            return res
        if pagina in vistas:
            break
        vistas.add(pagina)
    raise ErroGoogleOAuth("paginação sem fim")


def listar_eventos(conta: str, calendario_id: str, sync_token: str | None, janela: dict, token: Callable[[str], str],
                   http=_http_real) -> ResultadoEventos:
    """Eventos (instâncias, `singleEvents=true`) do calendário. `janela` = {"de": ISO, "ate": ISO} em UTC.
    Com `sync_token` vem só o que mudou (e os cancelados); 410 → recarga completa da janela (`recarga_completa=True`)."""
    conta = conta_valida(conta)
    if not isinstance(calendario_id, str) or not _CALENDARIO.match(calendario_id):
        raise ErroGoogleOAuth("calendário inválido")
    if not isinstance(janela, dict) or not janela.get("de") or not janela.get("ate"):
        raise ErroGoogleOAuth("janela inválida")
    res = _ler(conta, calendario_id, sync_token, janela, token, http) if sync_token else None
    if res is not None:
        return res
    recarga = bool(sync_token)
    res = _ler(conta, calendario_id, None, janela, token, http)
    res.recarga_completa = recarga
    return res


class GoogleAgenda:
    """Objeto da ponte (JSON puro). Sem o token provider nada sai."""

    def __init__(self, token: Callable[[str], str], http=_http_real):
        self._token, self._http = token, http

    def __repr__(self):
        return "GoogleAgenda(<oculto>)"

    def listar_calendarios(self, conta: str) -> list[dict]:
        return listar_calendarios(conta, self._token, self._http)

    def evento_criar(self, conta: str, chave: str, evento: dict) -> dict:
        return evento_criar(conta, chave, evento, self._token, self._http)

    def listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> dict:
        return asdict(listar_eventos(conta, calendario_id, sync_token, janela, self._token, self._http))


def google_agenda_do_ambiente(env) -> GoogleAgenda | None:
    """None ("não configurada") sem o cliente OAuth do Google no ambiente do serviço."""
    cred = credenciais_do_ambiente(env)
    if cred is None:
        return None
    return GoogleAgenda(TokenOAuth(cred[0], cred[1], env))
