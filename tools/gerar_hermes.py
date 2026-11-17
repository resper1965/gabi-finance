"""Regera em docs/fontes/hermes.md a lista `tools.include` do Hermes (a partir dos escopos; explícita e testada) e a lista do que sai do
`include` do `gabi_brain` na virada (as do Hermes menos as que existem nos dois servidores). Uso: python -m tools.gerar_hermes"""
import re
from pathlib import Path

from gabi.mcp.servidor import ferramentas_do_hermes

DOC = Path(__file__).resolve().parent.parent / "docs" / "fontes" / "hermes.md"
# existem no gabi_brain e no gabi_finance com o mesmo nome: ficam no include dos dois (dinheiro vem do finance; o resto, do brain)
NOS_DOIS = ("avisos_abertos", "decisao_responder", "decisoes_abertas", "decisoes_recentes", "resumo_manha")
CABECALHO_TIRAR = "# tirar do include do gabi_brain:\n"


def lista_atual() -> str:
    return "\n".join(f"      - {n}" for n in ferramentas_do_hermes())


def tirar_do_brain() -> list[str]:
    """Só de dinheiro: o gabi_brain deixa de oferecê-las (com GABI_SEM_FINANCEIRO=1 ele também não fala mais de dinheiro)."""
    return [n for n in ferramentas_do_hermes() if n not in NOS_DOIS]


def lista_tirar() -> str:
    return "\n".join(f"- {n}" for n in tirar_do_brain())


if __name__ == "__main__":
    s = DOC.read_text(encoding="utf-8")
    s = re.sub(r"(      include:\n)(?:      - .*\n?)+", lambda m: m.group(1) + lista_atual() + "\n", s)
    s = re.sub(r"(" + re.escape(CABECALHO_TIRAR) + r")(?:- .*\n?)+", lambda m: m.group(1) + lista_tirar() + "\n", s)
    DOC.write_text(s, encoding="utf-8")
    print("ok")
