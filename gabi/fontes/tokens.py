"""Tokens de acesso do Graph e do Google a partir do ambiente (R5: só variáveis de ambiente e arquivos de chave; nada no código ou no banco).
Cada `token_*` devolve um callable com cache até perto do vencimento, no formato que `Graph`/`Google` esperam. Sem rede nos testes: `http` injetável.
Variáveis: GRAPH_TENANT, GRAPH_CLIENT_ID, GRAPH_CERT_KEY_FILE, GRAPH_CERT_X5T · GOOGLE_SA_EMAIL, GOOGLE_SA_KEY_FILE, GOOGLE_SA_DOMINIOS (bekaa.eu,esper.ws) ·
GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_REFRESH_<ENDEREÇO> (ex.: GOOGLE_REFRESH_GABI_NESS_COM_BR). Consome: fontes.graph, fontes.google."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from gabi.fontes.google import ErroGoogle, Google, TOKEN_URL, assertion_servico
from gabi.fontes.graph import ErroGraph, Graph, LOGIN, assertion_certificado

ESCOPOS_GOOGLE = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose",
                  "https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/tasks"]
ESCOPO_GRAPH = "https://graph.microsoft.com/.default"
MARGEM = 120


def _form_real(url: str, campos: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(campos).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except OSError as e:
        raise ConnectionError(f"fonte indisponível: {type(e).__name__}") from None


def _com_cache(pedir: Callable[[], tuple[int, dict]], erro: type[Exception], relogio: Callable[[], float]) -> Callable[[], str]:
    guardado: dict = {}

    def token() -> str:
        if guardado.get("expira", 0) - MARGEM > relogio():
            return guardado["valor"]
        status, resp = pedir()
        if status >= 400 or "access_token" not in resp:
            raise erro(f"token -> {status}: {resp.get('error', '?')}")  # "-> 400/401" faz a rodada pedir reconexão
        guardado.update(valor=resp["access_token"], expira=relogio() + int(resp.get("expires_in", 3000)))
        return guardado["valor"]
    return token


def token_graph(tenant: str, client_id: str, chave_pem: bytes, x5t: str, *, http=_form_real, relogio=time.time) -> Callable[[], str]:
    def pedir():
        return http(f"{LOGIN}/{tenant}/oauth2/v2.0/token", {
            "grant_type": "client_credentials", "client_id": client_id, "scope": ESCOPO_GRAPH,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion_certificado(tenant, client_id, chave_pem, x5t, int(relogio()))})
    return _com_cache(pedir, ErroGraph, relogio)


def token_google_servico(email_sa: str, chave_pem: str, usuario: str, *, http=_form_real, relogio=time.time) -> Callable[[], str]:
    def pedir():
        return http(TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                "assertion": assertion_servico(email_sa, chave_pem, usuario, ESCOPOS_GOOGLE, int(relogio()))})
    return _com_cache(pedir, ErroGoogle, relogio)


def token_google_oauth(client_id: str, client_secret: str, refresh_token: str, *, http=_form_real, relogio=time.time) -> Callable[[], str]:
    def pedir():
        return http(TOKEN_URL, {"grant_type": "refresh_token", "client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token})
    return _com_cache(pedir, ErroGoogle, relogio)


def nome_da_variavel(endereco: str) -> str:
    return "GOOGLE_REFRESH_" + re.sub(r"[^A-Z0-9]+", "_", endereco.upper()).strip("_")


def cliente_do_ambiente(env=None, *, http=_form_real, relogio=time.time) -> Callable[[dict], object | None]:
    """`cliente_de(caixa)` para `trabalho.rodada_trabalho.rodar`: None quando faltar credencial daquela caixa (vira aviso "reconectar")."""
    env = os.environ if env is None else env
    dominios = {d.strip().lower() for d in (env.get("GOOGLE_SA_DOMINIOS") or "").split(",") if d.strip()}
    graph = None

    def cliente(caixa: dict):
        nonlocal graph
        endereco = caixa["endereco"]
        if caixa["provedor"] == "graph":
            if graph is None:
                if not all(env.get(k) for k in ("GRAPH_TENANT", "GRAPH_CLIENT_ID", "GRAPH_CERT_KEY_FILE", "GRAPH_CERT_X5T")):
                    return None
                graph = Graph(token_graph(env["GRAPH_TENANT"], env["GRAPH_CLIENT_ID"], Path(env["GRAPH_CERT_KEY_FILE"]).read_bytes(),
                                          env["GRAPH_CERT_X5T"], http=http, relogio=relogio))
            return graph
        if endereco.rsplit("@", 1)[-1].lower() in dominios and env.get("GOOGLE_SA_EMAIL") and env.get("GOOGLE_SA_KEY_FILE"):
            return Google(token_google_servico(env["GOOGLE_SA_EMAIL"], Path(env["GOOGLE_SA_KEY_FILE"]).read_text(), endereco, http=http, relogio=relogio))
        refresh = env.get(nome_da_variavel(endereco))
        if refresh and env.get("GOOGLE_OAUTH_CLIENT_ID") and env.get("GOOGLE_OAUTH_CLIENT_SECRET"):
            return Google(token_google_oauth(env["GOOGLE_OAUTH_CLIENT_ID"], env["GOOGLE_OAUTH_CLIENT_SECRET"], refresh, http=http, relogio=relogio))
        return None
    return cliente
