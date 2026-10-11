"""Fábricas das fontes externas a partir do ambiente (R5: só variáveis de ambiente; nenhuma credencial no código ou no banco).
`None` = fonte não configurada (a API responde 503 `fonte_indisponivel`). Consome: fontes.nibo_escrita, fontes.paperless."""
import os

from gabi.fontes.nibo_escrita import NiboEscrita
from gabi.fontes.paperless import Paperless
from gabi.fontes.ponte import Ponte, PonteAgenda


def fontes_do_ambiente() -> dict:
    """Com GABI_FONTES_SOCKET (API e MCP, sem rede) as fontes vivem no serviço gabi-brain-fontes; sem ela, direto do ambiente."""
    caminho = os.environ.get("GABI_FONTES_SOCKET")
    if caminho:
        ok = lambda p: p if p.configurada() else None  # noqa: E731
        fontes = {n: (lambda n=n: ok(Ponte(caminho, n))) for n in ("nibo", "paperless", "google_contatos")}
        fontes["google_agenda"] = lambda: ok(PonteAgenda(caminho))  # validação da forma da resposta; só leitura
        return fontes
    return {
        "nibo": lambda: NiboEscrita(os.environ["NIBO_TOKEN"]) if os.environ.get("NIBO_TOKEN") else None,
        "paperless": lambda: Paperless(os.environ["PAPERLESS_URL"], os.environ["PAPERLESS_TOKEN"])
        if os.environ.get("PAPERLESS_URL") and os.environ.get("PAPERLESS_TOKEN") else None,
    }
