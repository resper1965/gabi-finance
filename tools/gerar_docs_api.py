"""Gera docs/api.md e docs/openapi.json a partir do CÓDIGO (rotas REST e ferramentas MCP): a doc não tem como desatualizar.

Uso: python tools/gerar_docs_api.py        (um teste falha se docs/api.md divergir do que este script gera)
"""
import asyncio
import json
import tempfile
from pathlib import Path

from gabi.api import criar_app
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp

RAIZ = Path(__file__).resolve().parent.parent
FORMATO = ("Erros: `{\"erro\": <codigo>, \"mensagem\": <pt-BR>}` com `requisicao_invalida` (400), `nao_autenticado` (401), `sem_escopo`/`nao_permitido` (403), "
           "`nao_encontrado` (404), `conflito`/`confirmacao_divergente` (409), `tipo_invalido` (415). Dinheiro: string decimal (\"1234.56\"), saída negativa. "
           "Toda leitura de dinheiro traz o envelope `{dados_ate, desatualizado, fontes, dados}` (dados_ate = última rodada CONFERIDA).")


def montar(banco: Path | None = None) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        banco = banco or Path(tmp) / "doc.db"
        app = criar_app(banco)
        mcp = criar_mcp(banco, hosts=["127.0.0.1:8081"])
        openapi = app.openapi()  # o OpenAPI enumera também os routers incluídos (app.routes não)
        rotas = []
        for caminho, ops in openapi["paths"].items():
            if caminho.startswith("/api/"):
                for metodo, op in ops.items():
                    texto = (op.get("description") or op.get("summary") or "").strip().splitlines()
                    rotas.append((caminho, metodo.upper(), texto[0].strip() if texto else ""))
        rotas.sort()
        ferramentas = asyncio.run(mcp.servidor.list_tools())
        linhas = ["# API do gabi.brain (gerado do código; não editar à mão)", "", FORMATO, "",
                  "## REST (`/api/...`, só por `tailscale serve`; nível `boss` salvo indicação)", "",
                  "| Método | Rota | O que faz |", "|---|---|---|"]
        linhas += [f"| {m} | `{p}` | {d} |" for p, m, d in rotas]
        linhas += ["", "## MCP (`/mcp`, Streamable HTTP, `Authorization: Bearer <token>`; só leitura)", "",
                   "| Ferramenta | Escopo | Entrada | O que faz |", "|---|---|---|---|"]
        for t in sorted(ferramentas, key=lambda t: t.name):
            props = (t.input_schema or {}).get("properties", {}) if hasattr(t, "input_schema") else (t.inputSchema or {}).get("properties", {})
            entrada = ", ".join(sorted(props)) or "—"
            linhas.append(f"| `{t.name}` | `{ESCOPOS_FERRAMENTAS[t.name]}` | {entrada} | {(t.description or '').strip().splitlines()[0]} |")
        linhas += ["", "Não existem ferramentas de enviar, pagar, apagar, aprovar nem ligar regra (R13).", ""]
        return "\n".join(linhas), openapi


if __name__ == "__main__":
    md, openapi = montar()
    (RAIZ / "docs").mkdir(exist_ok=True)
    (RAIZ / "docs" / "api.md").write_text(md, encoding="utf-8")
    (RAIZ / "docs" / "openapi.json").write_text(json.dumps(openapi, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"docs/api.md ({md.count(chr(10))} linhas) e docs/openapi.json gerados")
