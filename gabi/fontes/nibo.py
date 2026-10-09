"""Cliente REST do Nibo (API Empresa), SOMENTE LEITURA. Docs: docs/fontes/nibo.md.

R2/R13: nenhum método de escrita ou exclusão aqui (a única gravação externa fica em cobrar/lote_nibo.py, T2.4).
R5: o token vem de quem instancia (NIBO_TOKEN, ambiente) e nunca entra em erro ou log. Consome: nada.
"""
import datetime as dt
import json
import urllib.error
import urllib.request
from typing import Callable, Iterator
from urllib.parse import quote, urlencode

BASE = "https://api.nibo.com.br/empresas/v1"
TOP = 500
# Rotas confirmadas por referencias/nibo_api.md: organizations, accounts, schedules, nfse, accounts/{id}/views/statement.
# NÃO VERIFICADAS (docs 'a abrir antes de codar', conferir com o token real no G8): partners, customers, categories.
ROTAS_A_CONFIRMAR = {"socios": "/partners", "clientes": "/customers", "categorias": "/categories"}

Http = Callable[..., "tuple[int, object]"]  # (metodo, url, corpo, cabecalhos) -> (status, json)


class ErroNibo(Exception):
    pass


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, {"message": e.reason}
    except OSError as e:
        raise ErroNibo(f"Nibo indisponível: {type(e).__name__}") from None


class Nibo:
    def __init__(self, token: str, base: str = BASE, *, http: Http | None = None):
        self._token, self.base, self._http = token, base.rstrip("/"), http or _http_real

    def _get(self, caminho: str, consulta: dict | None = None):
        url = self.base + caminho + ("?" + urlencode(consulta, quote_via=quote) if consulta else "")
        status, resp = self._http("GET", url, None, {"ApiToken": self._token})  # header ApiToken, nunca Authorization
        if status >= 400:
            detalhe = ""
            if isinstance(resp, dict):
                detalhe = resp.get("error_description") or resp.get("messageDetail") or resp.get("message") or ""
            raise ErroNibo(f"GET {caminho} -> {status}" + (f": {detalhe}" if detalhe else ""))
        return resp

    def _paginar(self, caminho: str, orderby: str, filtro: str | None = None, extra: dict | None = None) -> Iterator[dict]:
        """OData: $orderby obrigatório para paginar; até 500 por consulta ($top), avançando por $skip."""
        skip = 0
        while True:
            q = {**(extra or {}), "$orderby": orderby, "$top": TOP, "$skip": skip}
            if filtro:
                q["$filter"] = filtro
            resp = self._get(caminho, q)
            itens = resp.get("items", []) if isinstance(resp, dict) else resp
            yield from itens
            if len(itens) < TOP:
                return
            skip += TOP

    def organizations(self) -> list[dict]:
        return list(self._paginar("/organizations", "name"))

    def contas(self) -> list[dict]:
        return list(self._paginar("/accounts", "name"))

    def agendamentos(self, desde_update: dt.datetime, tipo: str | None) -> Iterator[dict]:
        """A pagar (`Debit`) e a receber (`Credit`), incremental por updateDate."""
        filtro = f"updateDate gt {desde_update.strftime('%Y-%m-%dT%H:%M:%S')}"
        if tipo:
            if tipo not in ("Debit", "Credit"):
                raise ValueError("tipo deve ser Debit ou Credit")
            filtro += f" and type eq '{tipo}'"
        return self._paginar("/schedules", "updateDate", filtro)

    def extrato(self, account_id: str, de: dt.date, ate: dt.date) -> list[dict]:
        resp = self._get(f"/accounts/{quote(str(account_id), safe='')}/views/statement", {"startDate": de.isoformat(), "endDate": ate.isoformat()})
        return resp.get("items", []) if isinstance(resp, dict) else list(resp)

    def nfse(self, desde: dt.date) -> Iterator[dict]:
        return self._paginar("/nfse", "emissionDate", f"emissionDate ge {desde.isoformat()}")

    def socios(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["socios"], "name"))

    def clientes(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["clientes"], "name"))

    def categorias(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["categorias"], "name"))
