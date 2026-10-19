"""Microsoft Graph da ness (resper@ness.com.br), SÓ leitura: contatos e agenda. Só o serviço `gabi-brain-fontes` tem rede e segredos (R5);
o resto do brain chega aqui pela ponte (`PonteGraph`). Autenticação do app por client credentials com secret (M365_TENANT_ID, M365_CLIENT_ID,
M365_CLIENT_SECRET no ambiente do serviço). O app tem permissão no tenant inteiro: a conta lida vem sempre de `M365_CONTAS` (padrão só
resper@ness.com.br), nunca de entrada livre. Segredo, token e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/graph-ness.md."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Callable

from gabi.fontes.google_agenda import ResultadoEventos
from gabi.fontes.google_contatos import MAX_EMAILS, _EMAIL

BASE = "https://graph.microsoft.com/v1.0"
HOST = "https://graph.microsoft.com/"
LOGIN = "https://login.microsoftonline.com"
MAX_PAGINAS = 200
FOLGA_S = 300
CONTAS_PADRAO = ["resper@ness.com.br"]
_CALENDARIO = re.compile(r"^[A-Za-z0-9=_.-]{1,300}$")  # "primary" ou id do Graph (base64 com "="): nunca "/" nem espaço


class ErroGraphNess(Exception):
    """Erro tipado da fonte: só texto curto, sem segredo e sem corpo de resposta."""


class _ErroStatus(ErroGraphNess):
    """Erro de status HTTP do Graph (a mensagem é a mesma de ErroGraphNess); `status` deixa o 410 do delta ser tratado sem olhar texto."""

    def __init__(self, mensagem: str, status: int):
        super().__init__(mensagem)
        self.status = status


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    """(status, json). O corpo de um erro NUNCA é lido (pode ecoar segredo ou texto de evento). A falha só é registrada no `except`; o erro
    tipado sai depois do bloco (sem __context__)."""
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    falha = None
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        codigo = e.code
        try:
            e.close()
        except Exception:  # noqa: BLE001
            pass
        return codigo, {}
    except (OSError, ValueError) as e:
        falha = type(e).__name__
    raise ErroGraphNess(f"Graph indisponível: {falha}")


def _chamar(http, metodo, url, corpo, cab):
    """Erro de rede do http injetado vira o erro tipado, fora do `except` (sem causa nem contexto)."""
    falha = None
    try:
        return http(metodo, url, corpo, cab)
    except ErroGraphNess:
        raise
    except Exception as e:  # noqa: BLE001
        falha = type(e).__name__
    raise ErroGraphNess(f"Graph indisponível: {falha}")


class TokenApp:
    """token() -> access token do app. Guarda em memória até FOLGA_S antes de expirar."""

    def __init__(self, tenant: str, client_id: str, secret: str, http=_http_real, agora=time.time):
        self._tenant, self._id, self._secret, self._http, self._agora = tenant, client_id, secret, http, agora
        self._cache: tuple[str, float] | None = None

    def __repr__(self):
        return "TokenApp(<oculto>)"

    def __call__(self) -> str:
        if self._cache and self._agora() < self._cache[1]:
            return self._cache[0]
        corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret,
                                        "scope": "https://graph.microsoft.com/.default"}).encode()
        url = f"{LOGIN}/{urllib.parse.quote(self._tenant, safe='')}/oauth2/v2.0/token"
        status, resp = _chamar(self._http, "POST", url, corpo, {"Content-Type": "application/x-www-form-urlencoded"})
        if status >= 400:
            raise ErroGraphNess(f"troca de token -> {status}")
        acc = resp.get("access_token") if isinstance(resp, dict) else None
        exp = resp.get("expires_in") if isinstance(resp, dict) else None
        if not isinstance(acc, str) or not acc or isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise ErroGraphNess("resposta inválida na troca de token")
        self._cache = (acc, self._agora() + exp - FOLGA_S)
        return acc

    def invalidar(self) -> None:
        self._cache = None


class GraphNess:
    """Objeto da ponte (JSON puro, só GET). Sem o token provider nada sai."""

    def __init__(self, token: Callable[[], str], contas: list[str], http=_http_real):
        self._token, self._contas, self._http = token, [c.lower() for c in contas], http

    def __repr__(self):
        return "GraphNess(<oculto>)"

    def contas(self) -> list[str]:
        return list(self._contas)

    def _conta(self, conta) -> str:
        if not isinstance(conta, str) or conta.lower() not in self._contas:
            raise ErroGraphNess("conta não permitida")
        return conta.lower()

    def _get(self, url: str, extra: dict | None = None) -> dict:
        """GET autenticado; só para o host do Graph (o link pode vir do banco ou da resposta). Um 401 invalida o token e repete UMA vez."""
        if not isinstance(url, str) or not url.startswith(HOST):
            raise ErroGraphNess("link inválido")
        caminho = urllib.parse.urlsplit(url).path
        for tentativa in (1, 2):
            cab = {"Authorization": f"Bearer {self._token()}", **(extra or {})}
            status, resp = _chamar(self._http, "GET", url, None, cab)
            if status == 401 and tentativa == 1 and hasattr(self._token, "invalidar"):
                self._token.invalidar()
                continue
            break
        if status >= 400:
            raise _ErroStatus(f"GET {caminho} -> {status}", status)
        if not isinstance(resp, dict):
            raise ErroGraphNess("resposta inválida do Graph")
        return resp


    def listar_calendarios(self, conta: str) -> list[dict]:
        """[{id, nome, principal}] dos calendários da conta."""
        conta = self._conta(conta)
        saida = []
        for pagina in self._paginas(f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/calendars"):
            for c in pagina.get("value") or []:
                if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]:
                    saida.append({"id": c["id"], "nome": c["name"] if isinstance(c.get("name"), str) else None,
                                  "principal": c.get("isDefaultCalendar") is True})
        return saida

    def _delta(self, url: str) -> tuple[list[dict], str]:
        """Todas as páginas do delta -> (itens, deltaLink). Sem deltaLink no fim a resposta é inválida."""
        itens, delta = [], None
        for pagina in self._paginas(url, {"Prefer": 'outlook.timezone="UTC", odata.maxpagesize=200'}):
            itens += [i for i in pagina.get("value") or [] if isinstance(i, dict)]
            delta = pagina.get("@odata.deltaLink")
        if not isinstance(delta, str) or not delta:
            raise ErroGraphNess("resposta inválida do Graph")
        return itens, delta

    def listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> dict:
        """Eventos (instâncias) do calendário na `janela` ({"de","ate"} ISO UTC); com `sync_token` (o deltaLink anterior) vem só o que mudou.
        410 numa carga incremental → recarga completa (`recarga_completa=True`). Devolve JSON puro (`asdict(ResultadoEventos)`)."""
        conta = self._conta(conta)
        if calendario_id != "primary" and not (isinstance(calendario_id, str) and _CALENDARIO.match(calendario_id)):
            raise ErroGraphNess("calendário inválido")
        if not isinstance(janela, dict) or not janela.get("de") or not janela.get("ate"):
            raise ErroGraphNess("janela inválida")
        if sync_token is not None and not (isinstance(sync_token, str) and sync_token.startswith(HOST)):
            raise ErroGraphNess("token de sincronização inválido")
        base = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}"
        if calendario_id != "primary":
            base += f"/calendars/{urllib.parse.quote(calendario_id, safe='')}"
        completa = f"{base}/calendarView/delta?" + urllib.parse.urlencode({"startDateTime": janela["de"], "endDateTime": janela["ate"]})
        recarga = False
        try:
            itens, delta = self._delta(sync_token or completa)
        except _ErroStatus as e:
            if not (sync_token and e.status == 410):
                raise
            recarga = True
            itens, delta = self._delta(completa)
        res = ResultadoEventos(novo_sync_token=delta, recarga_completa=recarga)
        for item in itens:
            if not isinstance(item.get("id"), str) or not item["id"]:
                continue
            if "@removed" in item or item.get("isCancelled") is True or _recusado_por_mim(item):
                res.cancelados.append(item["id"])  # recusado some do Outlook: some daqui (e apaga a linha já gravada)
            else:
                res.eventos.append(_evento(item))
        return asdict(res)

    def _paginas(self, url: str, extra: dict | None = None):
        """Cada página (dict) seguindo `@odata.nextLink`; link repetido ou mais de MAX_PAGINAS páginas é erro."""
        vistos = set()
        for _ in range(MAX_PAGINAS):
            resp = self._get(url, extra)
            yield resp
            url = resp.get("@odata.nextLink")
            if not url:
                return
            if url in vistos:
                break
            vistos.add(url)
        raise ErroGraphNess("paginação sem fim")

    def contatos(self, conta: str) -> list[dict]:
        """[{nome, telefone[, emails]}] como os contatos do Google: um item por telefone (celular, casa, trabalho), cada um com os e-mails do contato;
        contato só com e-mail vira um item com `telefone: None`. Só nome, telefone e e-mail são lidos."""
        conta = self._conta(conta)
        campos = "displayName,mobilePhone,homePhones,businessPhones,emailAddresses"
        url = f"{BASE}/users/{urllib.parse.quote(conta, safe='')}/contacts?$select={campos}&$top=100"
        saida = []
        for pagina in self._paginas(url):
            for p in pagina.get("value") or []:
                if not isinstance(p, dict):
                    continue
                nome = p.get("displayName")
                nome = nome if isinstance(nome, str) and nome.strip() else None
                emails = _emails(p.get("emailAddresses"))
                telefones = [t for t in [p.get("mobilePhone"), *(p.get("homePhones") or []), *(p.get("businessPhones") or [])]
                             if isinstance(t, str) and t.strip()]
                for t in telefones:
                    item = {"nome": nome, "telefone": t}
                    if emails:
                        item["emails"] = list(emails)
                    saida.append(item)
                if emails and not telefones:
                    saida.append({"nome": nome, "telefone": None, "emails": emails})
        return saida


def _hora(campo, dia_inteiro: bool):
    """`start`/`end` do Graph (UTC, `Prefer: outlook.timezone="UTC"`) -> formato do Google que `tempo.de_google` entende; None se inválido."""
    texto = campo.get("dateTime") if isinstance(campo, dict) else None
    if not isinstance(texto, str) or len(texto) < 19:
        return None
    return {"date": texto[:10]} if dia_inteiro else {"dateTime": texto[:19] + "Z"}


def _evento(item: dict) -> dict:
    dia = item.get("isAllDay") is True
    participantes = item.get("attendees")
    juntar = (item.get("onlineMeeting") or {}).get("joinUrl") if isinstance(item.get("onlineMeeting"), dict) else None
    texto = lambda v: v if isinstance(v, str) else None  # noqa: E731
    return {"externo_id": item["id"], "inicio": _hora(item.get("start"), dia), "fim": _hora(item.get("end"), dia),
            "titulo": texto(item.get("subject")),
            "link_reuniao": juntar if isinstance(juntar, str) and juntar.startswith("https://") else None,
            "participantes_qtd": len(participantes) if isinstance(participantes, list) else 0,
            "status": "confirmed", "etag": texto(item.get("@odata.etag")), "atualizado_origem": texto(item.get("lastModifiedDateTime")),
            "privado": item.get("sensitivity") in ("private", "confidential"),
            "ical_uid": texto(item.get("iCalUId")) or None, "livre": item.get("showAs") == "free"}


def _recusado_por_mim(item: dict) -> bool:
    r = item.get("responseStatus")
    return isinstance(r, dict) and r.get("response") == "declined"


def _emails(lista) -> list[str]:
    """Endereços válidos em minúsculas, sem repetir, no máximo MAX_EMAILS."""
    achados = []
    for e in lista or []:
        v = e.get("address") if isinstance(e, dict) else None
        if isinstance(v, str) and _EMAIL.match(v.strip()):
            achados.append(v.strip().lower())
    return list(dict.fromkeys(achados))[:MAX_EMAILS]


def graph_ness_do_ambiente(env) -> GraphNess | None:
    """None ("não configurada") sem tenant, client id e secret no ambiente do serviço."""
    t, i, s = env.get("M365_TENANT_ID"), env.get("M365_CLIENT_ID"), env.get("M365_CLIENT_SECRET")
    if not (t and i and s):
        return None
    contas = [c.strip() for c in (env.get("M365_CONTAS") or "").split(",") if c.strip()] or list(CONTAS_PADRAO)
    return GraphNess(TokenApp(t, i, s), contas)
