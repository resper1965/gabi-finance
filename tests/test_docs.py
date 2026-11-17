"""A documentação não pode ficar para trás do código: todo módulo de gabi/, toda ferramenta MCP e toda tabela do banco migrado têm de aparecer em
docs/modulos.md, docs/mcp.md e docs/dados.md; os links, os âncoras e os caminhos citados nos documentos principais têm de existir."""
import asyncio
import re
import tempfile
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

RAIZ = Path(__file__).parent.parent
DOCS = RAIZ / "docs"
# documentos escritos para o gabi-finance (os de docs/historico, docs/corte e docs/superpowers são registro e não são conferidos)
PRINCIPAIS = [RAIZ / "README.md", RAIZ / "painel" / "README.md", *(DOCS / n for n in (
    "ARQUITETURA.md", "STATUS.md", "runbook.md", "virada.md", "modulos.md", "dados.md", "mcp.md", "painel.md", "operacao.md", "api.md"))]
PRINCIPAIS += [DOCS / "adr" / "039-corte-gabi-finance.md", DOCS / "adr" / "README.md"]


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _modulos() -> list[str]:
    achados = []
    for arq in sorted((RAIZ / "gabi").rglob("*.py")):
        rel = arq.relative_to(RAIZ).with_suffix("")
        if "painel" in rel.parts or "__pycache__" in rel.parts:
            continue
        partes = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        achados.append(".".join(partes))
    return achados


def test_todo_modulo_de_gabi_esta_em_modulos_md():
    texto = _ler(DOCS / "modulos.md")
    falta = [m for m in _modulos() if f"### `{m}`" not in texto]
    assert falta == [], f"módulos sem verbete em docs/modulos.md: {falta}"


def test_modulos_md_nao_descreve_modulo_que_nao_existe():
    existentes = set(_modulos())
    citados = set(re.findall(r"^### `([^`]+)`", _ler(DOCS / "modulos.md"), re.M))
    assert citados <= existentes, f"verbetes de módulos que não existem mais: {sorted(citados - existentes)}"


def test_toda_ferramenta_mcp_esta_em_mcp_md():
    from gabi.mcp.servidor import criar_mcp
    with tempfile.TemporaryDirectory() as t:
        nomes = {x.name for x in asyncio.run(criar_mcp(Path(t) / "x.db", ["127.0.0.1:8082"]).servidor.list_tools())}
    texto = _ler(DOCS / "mcp.md")
    citadas = set(re.findall(r"^### `([^`]+)`", texto, re.M))
    assert nomes - citadas == set(), f"ferramentas sem verbete em docs/mcp.md: {sorted(nomes - citadas)}"
    assert citadas - nomes == set(), f"docs/mcp.md descreve ferramentas que não existem: {sorted(citadas - nomes)}"


def test_toda_tabela_do_banco_migrado_esta_em_dados_md(tmp_path):
    con = conectar(tmp_path / "t.db")
    migrar(con, RAIZ / "migrations")
    tabelas = {r[0] for r in con.execute("select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%'")}
    citadas = set(re.findall(r"^### `([^`]+)`", _ler(DOCS / "dados.md"), re.M))
    assert tabelas - citadas == set(), f"tabelas sem descrição em docs/dados.md: {sorted(tabelas - citadas)}"
    assert citadas - tabelas == set(), f"docs/dados.md descreve tabelas que não existem: {sorted(citadas - tabelas)}"


def test_toda_tela_do_painel_esta_em_painel_md():
    texto = _ler(DOCS / "painel.md")
    telas = [p.relative_to(RAIZ / "painel" / "src" / "telas").with_suffix("").as_posix() for p in (RAIZ / "painel" / "src" / "telas").rglob("*.tsx")]
    falta = [t for t in telas if t.split("/")[-1] not in texto]
    assert falta == [], f"telas sem menção em docs/painel.md: {falta}"


def test_toda_unidade_do_deploy_esta_em_operacao_md():
    texto = _ler(DOCS / "operacao.md")
    unidades = {p.name.rsplit(".", 1)[0] for p in (RAIZ / "deploy").glob("gabi-finance-*.service")} | {p.name.rsplit(".", 1)[0] for p in (RAIZ / "deploy").glob("gabi-finance-*.timer")}
    falta = [u for u in sorted(unidades) if u not in texto and u.replace("@", "@.") not in texto]
    assert falta == [], f"unidades de deploy/ sem menção em docs/operacao.md: {falta}"


def test_documentos_principais_existem_e_nao_estao_vazios():
    for caminho in PRINCIPAIS:
        assert caminho.is_file() and len(_ler(caminho).strip()) > 200, f"{caminho.relative_to(RAIZ)} falta ou está vazio"


def test_readme_tem_o_estado_e_aponta_para_a_virada():
    r = _ler(RAIZ / "README.md")
    assert "Estado" in r and "docs/virada.md" in r


def test_status_esta_zerado_e_guarda_o_historico_do_brain():
    assert (DOCS / "historico" / "gabi-brain" / "STATUS-ate-2026-11-17.md").is_file()
    assert "Pendências" in _ler(DOCS / "STATUS.md")


def _ancoras(texto: str) -> set[str]:
    achadas = set(re.findall(r"\{#([\w-]+)\}", texto))
    for titulo in re.findall(r"^#{1,6}\s+(.*)$", texto, re.M):
        titulo = re.sub(r"\s*\{#[\w-]+\}\s*$", "", titulo).strip().lower()
        titulo = re.sub(r"[`*]", "", titulo)
        slug = re.sub(r"[^\w\s-]", "", titulo, flags=re.U).replace(" ", "-")
        achadas.add(slug)
    return achadas


def _links(texto: str):
    sem_codigo = re.sub(r"```.*?```", "", texto, flags=re.S)
    sem_codigo = re.sub(r"`[^`\n]*`", "", sem_codigo)
    return re.findall(r"\]\(([^)\s]+)\)", sem_codigo)


@pytest.mark.parametrize("caminho", [p for p in PRINCIPAIS if p.name != "api.md"], ids=lambda p: p.relative_to(RAIZ).as_posix())
def test_links_relativos_apontam_para_arquivo_e_ancora_que_existem(caminho):
    quebrados = []
    for alvo in _links(_ler(caminho)):
        if alvo.startswith(("http://", "https://", "mailto:")):
            continue
        arquivo, _, ancora = alvo.partition("#")
        destino = (caminho.parent / arquivo).resolve() if arquivo else caminho
        if not destino.exists():
            quebrados.append(alvo)
        elif ancora and destino.is_file() and destino.suffix == ".md" and ancora not in _ancoras(_ler(destino)):
            quebrados.append(alvo)
    assert quebrados == [], f"links quebrados em {caminho.relative_to(RAIZ)}: {quebrados}"


EXTENSOES = r"(?:py|sh|service|timer|sql|json|csv|md|tsx|ts)"


@pytest.mark.parametrize("caminho", [p for p in PRINCIPAIS if p.name not in ("api.md", "modulos.md")], ids=lambda p: p.relative_to(RAIZ).as_posix())
def test_caminhos_de_arquivo_citados_existem(caminho):
    texto = _ler(caminho)
    citados = set(re.findall(r"`((?:gabi|tools|deploy|migrations|seeds|tests|painel/src|docs)/[A-Za-z0-9_./@-]+\." + EXTENSOES + r")`", texto))
    ausentes = sorted(c for c in citados if not (RAIZ / c).exists() and not (caminho.parent / c).exists() and "AAAA" not in c)
    assert ausentes == [], f"{caminho.relative_to(RAIZ)} cita arquivos que não existem: {ausentes}"


def test_comandos_python_m_citados_existem():
    ruins = []
    for caminho in PRINCIPAIS:
        for mod in set(re.findall(r"python3? -m ((?:gabi|tools)(?:\.[a-z_]+)+)", _ler(caminho))):
            if not ((RAIZ / (mod.replace(".", "/") + ".py")).exists() or (RAIZ / mod.replace(".", "/") / "__init__.py").exists()):
                ruins.append((caminho.name, mod))
    assert ruins == [], f"comandos `python -m` para módulos que não existem: {ruins}"
