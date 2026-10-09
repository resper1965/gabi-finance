"""Nibo: as ÚNICAS gravações do app (R2), usadas só pelo lote confirmado de cobrar/lote_nibo.py. Docs: docs/fontes/nibo.md.

Só criar agendamento a pagar ao sócio, anexar arquivo e baixar o pagamento; nada de exclusão ou edição. Consome: fontes.nibo."""
import json
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from gabi.fontes.nibo import ErroNibo, Nibo


def _multipart_real(url, nome, conteudo, cabecalhos):
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
        + conteudo + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(url, data=corpo, method="POST", headers={**cabecalhos, "Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.reason}
    except OSError as e:
        raise ErroNibo(f"Nibo indisponível: {type(e).__name__}") from None


class NiboEscrita(Nibo):
    def __init__(self, token, base=None, *, http=None, http_arquivo=None):
        super().__init__(token, **({"base": base} if base else {}), http=http)
        self._http_arquivo = http_arquivo or _multipart_real

    def _post(self, caminho: str, corpo):
        status, resp = self._http("POST", self.base + caminho, corpo, {"ApiToken": self._token})
        if status >= 400:
            detalhe = (resp.get("error_description") or resp.get("messageDetail") or resp.get("message") or "") if isinstance(resp, dict) else ""
            raise ErroNibo(f"POST {caminho.split('?')[0]} -> {status}" + (f": {detalhe}" if detalhe else ""))
        return resp

    def agendamento_por_reference(self, reference: str) -> dict | None:
        """Leitura de idempotência: o agendamento com essa `reference`, se já existir."""
        itens = self._get("/schedules", {"$filter": f"reference eq '{reference}'", "$orderby": "updateDate", "$top": 1})
        itens = itens.get("items", []) if isinstance(itens, dict) else itens
        return itens[0] if itens else None

    def criar_agendamento_debito(self, *, stakeholder_id, valor_centavos, data, category_id, descricao, reference) -> str:
        r = self._post("/schedules/debit/FormatType=json", {
            "stakeholderId": stakeholder_id, "value": valor_centavos / 100, "dueDate": data, "scheduleDate": data, "accrualDate": data,
            "categoryId": category_id, "description": descricao, "reference": reference})
        return r["scheduleId"]

    def anexar_arquivo(self, schedule_id: str, nome: str, conteudo: bytes) -> None:
        status, resp = self._http_arquivo(self.base + "/files", nome, conteudo, {"ApiToken": self._token})
        if status >= 400:
            raise ErroNibo(f"POST /files -> {status}")
        self._post(f"/schedules/debit/{quote(str(schedule_id), safe='')}/files/attach", [resp[0]["fileId"]])

    def baixar_pagamento(self, schedule_id: str, *, account_id: str, data: str, valor_centavos: int, identifier: str) -> None:
        self._post(f"/schedules/debit/{quote(str(schedule_id), safe='')}/payments",
                   {"accountId": account_id, "date": data, "value": valor_centavos / 100, "identifier": identifier})
