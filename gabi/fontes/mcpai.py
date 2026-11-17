"""Cliente REST da mcp.ai (Open Finance, Pluggy): só leitura. Docs: docs/fontes/mcpai.md.

R13: as rotas `transactions/category` e `connections/disconnect` NUNCA são chamadas (falham antes da rede).
R5: a chave vem de MCPAI_KEY (ambiente) e nunca entra em erro ou log. Consome: nada.
"""
import json
import os
import time
import urllib.error
import urllib.request
from gabi.fontes._http import abrir
from typing import Callable

BASE = "https://api.mcp.ai/api/openfinance"
PROIBIDAS = {"transactions/category", "connections/disconnect"}

# nome da ferramenta (como o gabi-fin e o MCP da mcp.ai a chamam) -> rota REST (coleção Postman oficial)
FERRAMENTA_ROTA = {
    "openfinance_search_bank_connectors": "connectors/search", "openfinance_list_connections": "connections/list",
    "openfinance_get_item_status": "connections/status", "openfinance_force_sync": "connections/sync",
    "openfinance_disconnect_bank": "connections/disconnect", "openfinance_list_accounts": "accounts/list",
    "openfinance_get_accounts_detail": "accounts/detail", "openfinance_get_account_balance": "accounts/balance",
    "openfinance_list_transactions": "transactions/list", "openfinance_list_transactions_by_item": "transactions/by-item",
    "openfinance_provider_status": "provider/status", "openfinance_list_credit_card_bills": "credit-card-bills/list",
    "openfinance_get_credit_card_bill": "credit-card-bills/detail", "openfinance_list_investments": "investments/list",
    "openfinance_list_investment_transactions": "investments/transactions/list", "openfinance_list_loans": "loans/list",
    "openfinance_get_loan_detail": "loans/detail", "openfinance_list_categories": "categories/list",
    "openfinance_update_transaction_category": "transactions/category",
}

Post = Callable[[str, dict, dict], "tuple[int, dict, dict]"]  # (url, corpo, cabeçalhos) -> (status, corpo, cabeçalhos)


class RotaProibida(Exception):
    pass


class RotaDesconhecida(Exception):
    pass


class ErroMcpAi(Exception):
    """Erro da mcp.ai. `codigo` é nosso (estável); a mensagem nunca carrega a chave."""

    def __init__(self, codigo: str, http: int | None = None, retry_apos: float | None = None, connect_url: str | None = None):
        super().__init__(f"mcp.ai: {codigo}" + (f" (HTTP {http})" if http else ""))
        self.codigo, self.http, self.retry_apos, self.connect_url = codigo, http, retry_apos, connect_url


def _post_http(url: str, corpo: dict, cabecalhos: dict):
    req = urllib.request.Request(url, json.dumps(corpo).encode("utf-8"), cabecalhos, method="POST")
    try:
        with abrir(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            corpo_erro = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            corpo_erro = {}
        return e.code, corpo_erro, dict(e.headers or {})


def _codigo(status: int, corpo: dict) -> str:
    c = ((corpo.get("error") or {}).get("code") or "") if isinstance(corpo, dict) else ""
    if status == 409 and c == "not_connected":
        return "nao_conectado"
    if status == 401:
        return "nao_autenticado"
    if status == 403:
        return "escopo_da_chave" if c == "key_scope_mismatch" else "proibido"
    if status == 402:
        return "sem_creditos"
    if status == 429:
        return "limite_de_taxa"
    return f"erro_{status}" if status >= 400 else (c or "erro")


def chamar(rota: str, corpo: dict, *, post: Post | None = None, chave: str | None = None) -> dict:
    """Uma chamada REST. Devolve `result`. Levanta RotaProibida antes de qualquer rede, e ErroMcpAi nos erros."""
    if rota in PROIBIDAS:
        raise RotaProibida(f"rota proibida no gabi-finance: {rota}")
    chave = chave or os.environ.get("MCPAI_KEY")
    if not chave:
        raise ErroMcpAi("sem_chave")
    status, resposta, cab = (post or _post_http)(
        f"{BASE}/{rota}", corpo, {"Authorization": f"Bearer {chave}", "Content-Type": "application/json",
                                  "Accept": "application/json", "User-Agent": "gabi-finance/1.0"})
    resposta = resposta if isinstance(resposta, dict) else {}
    erro = resposta.get("error") if isinstance(resposta.get("error"), dict) else None
    if status >= 400 or erro or resposta.get("ok") is False:
        retry = None
        if cab.get("Retry-After") or cab.get("retry-after"):
            try:
                retry = float(cab.get("Retry-After") or cab.get("retry-after"))
            except ValueError:
                retry = None
        ms = ((erro or {}).get("details") or {}).get("retry_after_ms")
        if retry is None and ms:
            retry = ms / 1000
        raise ErroMcpAi(_codigo(status, resposta), http=status, retry_apos=retry,
                        connect_url=(erro or {}).get("connect_url"))
    return resposta.get("result", resposta)


class Cliente:
    """Chamável `cliente(ferramenta, args, tent=5)` com a semântica do gabi-fin: espaça as chamadas, repete 429/5xx/rede
    e devolve None se esgotar; erros definitivos (401/402/403/409) sobem na hora, sem repetir."""

    DEFINITIVOS = {"nao_conectado", "nao_autenticado", "escopo_da_chave", "proibido", "sem_creditos", "sem_chave"}

    def __init__(self, post: Post | None = None, chave: str | None = None, dorme: Callable[[float], None] = time.sleep,
                 intervalo: float = 1.2):
        self.post, self.chave, self.dorme, self.intervalo = post, chave, dorme, intervalo

    def __call__(self, ferramenta: str, args: dict, tent: int = 5):
        rota = FERRAMENTA_ROTA.get(ferramenta)
        if rota is None:
            raise RotaDesconhecida(ferramenta)
        if rota in PROIBIDAS:
            raise RotaProibida(f"ferramenta proibida no gabi-finance: {ferramenta}")
        for i in range(tent):
            self.dorme(self.intervalo)
            try:
                return chamar(rota, args, post=self.post, chave=self.chave)
            except ErroMcpAi as e:
                if e.codigo in self.DEFINITIVOS:
                    raise
                espera = e.retry_apos if e.retry_apos is not None else 5.0 * (i + 1)
                self.dorme(min(espera, 60.0))
            except OSError:
                self.dorme(5.0 * (i + 1))
        return None
