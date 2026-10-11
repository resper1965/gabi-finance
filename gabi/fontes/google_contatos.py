"""Contatos do Google (People API), SÓ leitura de nome e telefone. Só o serviço `gabi-brain-fontes` tem rede e segredos (R5); o resto do
brain chega aqui pela ponte (`PonteContatos`). Escopo `contacts.readonly`; `personFields=names,phoneNumbers` e nada mais (sem foto, e-mail,
endereço ou nota). Token por conta: OAuth do usuário com refresh token (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_<CONTA> no
ambiente do serviço). Segredo e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/google.md."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

ESCOPO = "https://www.googleapis.com/auth/contacts.readonly"
URL_CONTATOS = "https://people.googleapis.com/v1/people/me/connections"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CAMPOS = "names,phoneNumbers"
MAX_PAGINAS = 200
FOLGA_S = 60
_CONTA = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,120}$")


class ErroGoogleContatos(Exception):
    pass


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    """(status, json). Corpo `bytes` vai como está (formulário do token); o corpo de erro NUNCA é lido (pode ecoar segredo)."""
    dados = corpo if isinstance(corpo, bytes) else (json.dumps(corpo).encode() if corpo is not None else None)
    req = urllib.request.Request(url, data=dados, method=metodo, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (OSError, ValueError) as e:
        raise ErroGoogleContatos(f"Google indisponível: {type(e).__name__}") from None


def _chamar(http, metodo, url, corpo, cab):
    """Erro de rede do http injetado vira o erro tipado, fora do `except` (sem causa nem contexto)."""
    falha = None
    try:
        return http(metodo, url, corpo, cab)
    except ErroGoogleContatos:
        raise
    except Exception as e:  # noqa: BLE001
        falha = type(e).__name__
    raise ErroGoogleContatos(f"Google indisponível: {falha}")


def _conta_valida(conta) -> str:
    if not isinstance(conta, str) or not _CONTA.match(conta):
        raise ErroGoogleContatos("conta inválida")
    return conta


def nome_da_variavel(conta: str) -> str:
    """resper@gmail.com -> GOOGLE_REFRESH_RESPER_GMAIL_COM"""
    return "GOOGLE_REFRESH_" + re.sub(r"[^A-Za-z0-9]", "_", conta).upper()


class TokenOAuth:
    """token(conta) -> access token. Troca o refresh token da conta em TOKEN_URL e guarda o access token em memória até ~60 s antes de expirar."""

    def __init__(self, client_id: str, client_secret: str, ambiente, *, http=_http_real, relogio=time.time):
        self._id, self._secret, self._env, self._http, self._relogio = client_id, client_secret, ambiente, http, relogio
        self._cache: dict[str, tuple[str, float]] = {}
        self._trava = threading.Lock()

    def __repr__(self):
        return "TokenOAuth(<oculto>)"

    def __call__(self, conta: str) -> str:
        conta = _conta_valida(conta)
        with self._trava:
            c = self._cache.get(conta)
            if c and self._relogio() < c[1]:
                return c[0]
            refresh = self._env.get(nome_da_variavel(conta))
            if not refresh:
                raise ErroGoogleContatos(f"conta não autorizada: {conta}")
            corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": self._id, "client_secret": self._secret,
                                            "refresh_token": refresh}).encode()
            status, resp = _chamar(self._http, "POST", TOKEN_URL, corpo, {"Content-Type": "application/x-www-form-urlencoded"})
            if status in (400, 401):
                raise ErroGoogleContatos(f"conta não autorizada: {conta}")
            if status >= 400:
                raise ErroGoogleContatos(f"troca de token -> {status}")
            acc = resp.get("access_token") if isinstance(resp, dict) else None
            exp = resp.get("expires_in") if isinstance(resp, dict) else None
            if not isinstance(acc, str) or not acc or isinstance(exp, bool) or not isinstance(exp, (int, float)):
                raise ErroGoogleContatos("resposta inválida na troca de token")
            self._cache[conta] = (acc, self._relogio() + exp - FOLGA_S)
            return acc


def listar_contatos(conta: str, token: Callable[[str], str], http=_http_real) -> list[dict]:
    """Todas as páginas de people/me/connections -> [{nome, telefone}] (telefone cru; um item por telefone)."""
    conta = _conta_valida(conta)
    saida, pagina, vistas = [], None, set()
    for _ in range(MAX_PAGINAS):
        q = {"personFields": CAMPOS, "pageSize": "1000"}
        if pagina:
            q["pageToken"] = pagina
        url = URL_CONTATOS + "?" + urllib.parse.urlencode(q, safe=",")
        status, resp = _chamar(http, "GET", url, None, {"Authorization": f"Bearer {token(conta)}"})
        if status >= 400:
            raise ErroGoogleContatos(f"people.connections.list -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleContatos("resposta inválida do Google")
        for p in resp.get("connections") or []:
            if not isinstance(p, dict):
                continue
            nomes = p.get("names") or []
            nome = nomes[0].get("displayName") if nomes and isinstance(nomes[0], dict) else None
            for t in p.get("phoneNumbers") or []:
                if isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                    saida.append({"nome": nome if isinstance(nome, str) and nome.strip() else None, "telefone": t["value"]})
        pagina = resp.get("nextPageToken")
        if not pagina:
            return saida
        if pagina in vistas:
            break
        vistas.add(pagina)
    raise ErroGoogleContatos("paginação sem fim")


class GoogleContatos:
    """Objeto da ponte: `listar(conta)`. Sem o token provider nada sai."""

    def __init__(self, token: Callable[[str], str], http=_http_real):
        self._token, self._http = token, http

    def __repr__(self):
        return "GoogleContatos(<oculto>)"

    def listar(self, conta: str) -> list[dict]:
        return listar_contatos(conta, self._token, self._http)


def google_contatos_do_ambiente(env) -> GoogleContatos | None:
    """None ("não configurada") sem GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET."""
    if not env.get("GOOGLE_CLIENT_ID") or not env.get("GOOGLE_CLIENT_SECRET"):
        return None
    return GoogleContatos(TokenOAuth(env["GOOGLE_CLIENT_ID"], env["GOOGLE_CLIENT_SECRET"], env))
