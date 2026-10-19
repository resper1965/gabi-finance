"""Microsoft Graph da ness (resper@ness.com.br), SÓ leitura: contatos e agenda. Só o serviço `gabi-brain-fontes` tem rede e segredos (R5);
o resto do brain chega aqui pela ponte (`PonteGraph`). Autenticação do app por client credentials com secret (M365_TENANT_ID, M365_CLIENT_ID,
M365_CLIENT_SECRET no ambiente do serviço). O app tem permissão no tenant inteiro: a conta lida vem sempre de `M365_CONTAS` (padrão só
resper@ness.com.br), nunca de entrada livre. Segredo, token e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/graph-ness.md."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from gabi.fontes.google_contatos import MAX_EMAILS, _EMAIL

BASE = "https://graph.microsoft.com/v1.0"
HOST = "https://graph.microsoft.com/"
LOGIN = "https://login.microsoftonline.com"
MAX_PAGINAS = 200
FOLGA_S = 300
CONTAS_PADRAO = ["resper@ness.com.br"]


class ErroGraphNess(Exception):
    """Erro tipado da fonte: só texto curto, sem segredo e sem corpo de resposta."""


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
            raise ErroGraphNess(f"GET {caminho} -> {status}")
        if not isinstance(resp, dict):
            raise ErroGraphNess("resposta inválida do Graph")
        return resp


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
