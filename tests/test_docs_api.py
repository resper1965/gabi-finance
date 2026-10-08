"""A doc da API é gerada do código; estes testes impedem que ela fique defasada ou vazia."""
import tempfile
from pathlib import Path

from tools.gerar_docs_api import montar

RAIZ = Path(__file__).parent.parent


def test_docs_api_md_esta_em_dia_com_o_codigo():
    md, _ = montar()
    atual = (RAIZ / "docs" / "api.md").read_text(encoding="utf-8")
    assert atual == md, "docs/api.md está desatualizado: rode  python -m tools.gerar_docs_api  e commite"


def test_toda_rota_rest_tem_descricao_de_verdade():
    _, openapi = montar()
    sem = [f"{m.upper()} {p}" for p, ops in openapi["paths"].items() if p.startswith("/api/") for m, op in ops.items() if not (op.get("description") or "").strip()]
    assert sem == [], f"rotas sem docstring de uma linha: {sem}"


def test_toda_ferramenta_mcp_tem_escopo_declarado_e_descricao():
    import asyncio
    from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp
    from gabi.mcp.tokens import ESCOPOS
    with tempfile.TemporaryDirectory() as t:
        tools = asyncio.run(criar_mcp(Path(t) / "x.db", ["127.0.0.1:8081"]).servidor.list_tools())
    assert {x.name for x in tools} == set(ESCOPOS_FERRAMENTAS)
    assert set(ESCOPOS_FERRAMENTAS.values()) <= ESCOPOS and all((x.description or "").strip() for x in tools)
