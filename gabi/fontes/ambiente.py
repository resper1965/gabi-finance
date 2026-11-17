"""Fábricas das fontes externas a partir do ambiente (R5: só variáveis de ambiente; nenhuma credencial no código ou no banco).
`None` = fonte não configurada (a API responde 503 `fonte_indisponivel`). Consome: fontes.nibo_escrita, fontes.ponte."""
import os

from gabi.fontes.nibo_escrita import NiboEscrita
from gabi.fontes.ponte import Ponte


def fontes_do_ambiente() -> dict:
    """Com GABI_FONTES_SOCKET (API e MCP, sem rede) as fontes vivem no serviço de fontes; sem ela, direto do ambiente."""
    caminho = os.environ.get("GABI_FONTES_SOCKET")
    if caminho:
        ok = lambda p: p if p.configurada() else None  # noqa: E731
        return {"nibo": lambda: ok(Ponte(caminho, "nibo"))}
    return {
        "nibo": lambda: NiboEscrita(os.environ["NIBO_TOKEN"]) if os.environ.get("NIBO_TOKEN") else None,
    }
