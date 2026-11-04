"""OAuth do usuário para as fontes Google (contatos e agenda), compartilhado. Só o serviço `gabi-brain-fontes` tem rede e segredos (R5).
Um refresh token por conta (GOOGLE_REFRESH_<CONTA>) pode carregar VÁRIOS escopos (contacts.readonly + calendar.readonly + calendar.events, este só para criar evento aprovado): o Ricardo
refaz o consentimento uma vez e o mesmo token serve às duas fontes. Cliente OAuth: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET (aceita os nomes
legados GOOGLE_OAUTH_CLIENT_ID/SECRET). Segredo e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/google.md."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from gabi.fontes._http import abrir

TOKEN_URL = "https://oauth2.googleapis.com/token"
FOLGA_S = 60
_CONTA = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,120}$")


class ErroGoogleOAuth(Exception):
    """Erro tipado das fontes Google (contatos, agenda): só texto curto, sem segredo e sem corpo de resposta."""


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    """(status, json). Corpo `bytes` vai como está (formulário do token); o corpo de erro NUNCA é lido (pode ecoar segredo).
    A falha é só registrada no `except` e o erro tipado sai DEPOIS do bloco (sem __context__)."""
    dados = corpo if isinstance(corpo, bytes) else (json.dumps(corpo).encode() if corpo is not None else None)
    req = urllib.request.Request(url, data=dados, method=metodo, headers=cabecalhos or {})
    falha = None
    try:
        with abrir(req, timeout=60) as r:
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
    raise ErroGoogleOAuth(f"Google indisponível: {falha}")


def chamar(http, metodo, url, corpo, cab):
    """Erro de rede do http injetado vira o erro tipado, fora do `except` (sem causa nem contexto)."""
    falha = None
    try:
        return http(metodo, url, corpo, cab)
    except ErroGoogleOAuth:
        raise
    except Exception as e:  # noqa: BLE001
        falha = type(e).__name__
    raise ErroGoogleOAuth(f"Google indisponível: {falha}")


def conta_valida(conta) -> str:
    if not isinstance(conta, str) or not _CONTA.match(conta):
        raise ErroGoogleOAuth("conta inválida")
    return conta


def nome_da_variavel(conta: str) -> str:
    """resper@gmail.com -> GOOGLE_REFRESH_RESPER_GMAIL_COM"""
    return "GOOGLE_REFRESH_" + re.sub(r"[^A-Za-z0-9]", "_", conta).upper()


class TokenOAuth:
    """token(conta) -> access token. Troca o refresh token da conta em TOKEN_URL e guarda o access token em memória até ~60 s antes de expirar."""

    def __init__(self, client_id: str, client_secret: str, ambiente, *, http=_http_real, relogio=None):
        self._id, self._secret, self._env, self._http = client_id, client_secret, ambiente, http
        self._relogio = relogio or time.monotonic
        self._cache: dict[str, tuple[str, float]] = {}
        self._trava = threading.Lock()

    def __repr__(self):
        return "TokenOAuth(<oculto>)"

    def __call__(self, conta: str) -> str:
        conta = conta_valida(conta)
        with self._trava:
            c = self._cache.get(conta)
            if c and self._relogio() < c[1]:
                return c[0]
            refresh = self._env.get(nome_da_variavel(conta))
            if not refresh:
                raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
            corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": self._id, "client_secret": self._secret,
                                            "refresh_token": refresh}).encode()
            status, resp = chamar(self._http, "POST", TOKEN_URL, corpo, {"Content-Type": "application/x-www-form-urlencoded"})
            if status in (400, 401):
                raise ErroGoogleOAuth(f"token recusado: {conta}")
            if status >= 400:
                raise ErroGoogleOAuth(f"troca de token -> {status}")
            acc = resp.get("access_token") if isinstance(resp, dict) else None
            exp = resp.get("expires_in") if isinstance(resp, dict) else None
            if not isinstance(acc, str) or not acc or isinstance(exp, bool) or not isinstance(exp, (int, float)):
                raise ErroGoogleOAuth("resposta inválida na troca de token")
            self._cache[conta] = (acc, self._relogio() + exp - FOLGA_S)
            return acc


    def invalidar(self, conta: str) -> None:
        with self._trava:
            self._cache.pop(conta, None)


def credenciais_do_ambiente(env) -> tuple[str, str] | None:
    """(client_id, client_secret) ou None ("não configurada"); os nomes canônicos vencem os legados."""
    for i, s in (("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"), ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")):
        if env.get(i) and env.get(s):
            return env[i], env[s]
    return None
