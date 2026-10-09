"""Fábricas das fontes externas a partir do ambiente (R5: só variáveis de ambiente; nenhuma credencial no código ou no banco).
`None` = fonte não configurada (a API responde 503 `fonte_indisponivel`). Consome: fontes.nibo_escrita, fontes.paperless."""
import os

from gabi.fontes.nibo_escrita import NiboEscrita
from gabi.fontes.paperless import Paperless


def fontes_do_ambiente() -> dict:
    return {
        "nibo": lambda: NiboEscrita(os.environ["NIBO_TOKEN"]) if os.environ.get("NIBO_TOKEN") else None,
        "paperless": lambda: Paperless(os.environ["PAPERLESS_URL"], os.environ["PAPERLESS_TOKEN"])
        if os.environ.get("PAPERLESS_URL") and os.environ.get("PAPERLESS_TOKEN") else None,
    }
