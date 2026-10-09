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
# partners, customers, categories: CONFIRMADAS com o token real em 09/10/2026 (G8): GET 200, paginação OData e formato `items` ok.
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


HOST_ARQUIVOS = "https://arquivos.nibo.com.br/"


def _http_arquivo_real(url, cabecalhos):
    req = urllib.request.Request(url, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except OSError as e:
        raise ErroNibo(f"Nibo indisponível: {type(e).__name__}") from None


class Nibo:
    def __init__(self, token: str, base: str = BASE, *, http: Http | None = None, http_arquivo=None):
        self._token, self.base, self._http = token, base.rstrip("/"), http or _http_real
        self._http_arquivo = http_arquivo or _http_arquivo_real

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

    def agendamentos_a_receber(self) -> list[dict]:
        """Todos os agendamentos a receber (`/schedules/credit`): cada NFS-e aponta para um (isPaid/paidValue/openValue/value líquido)."""
        return list(self._paginar("/schedules/credit", "dueDate"))

    def extrato(self, account_id: str, de: dt.date, ate: dt.date) -> list[dict]:
        resp = self._get(f"/accounts/{quote(str(account_id), safe='')}/views/statement", {"startDate": de.isoformat(), "endDate": ate.isoformat()})
        return resp.get("items", []) if isinstance(resp, dict) else list(resp)

    def nfse(self, desde: dt.date) -> Iterator[dict]:
        """NFS-e emitidas (todas as situações) com createDate a partir de `desde`. O Nibo responde 500 a $orderby=emissionDate e a datas sem offset."""
        desde = dt.date.fromisoformat(desde) if isinstance(desde, str) else desde  # via ponte a data chega como texto ISO
        return self._paginar("/nfse", "createDate", f"createDate ge {desde.isoformat()}T00:00:00Z")

    def obter_arquivo(self, url: str) -> bytes:
        """PDF/XML de uma nota (pdfFileUrl/xmlFileUrl). Só o host de arquivos do Nibo: o token nunca vai para outra URL."""
        if not str(url).startswith(HOST_ARQUIVOS):
            raise ErroNibo("URL de arquivo fora do host do Nibo")
        status, corpo = self._http_arquivo(url, {"ApiToken": self._token})
        if status >= 400:
            raise ErroNibo(f"GET arquivo -> {status}")
        return corpo

    def socios(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["socios"], "name"))

    def clientes(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["clientes"], "name"))

    def categorias(self) -> list[dict]:
        return list(self._paginar(ROTAS_A_CONFIRMAR["categorias"], "name"))
