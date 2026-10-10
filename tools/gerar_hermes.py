"""Regera a lista `tools.include` do Hermes em docs/fontes/hermes.md a partir dos escopos (a lista é explícita e testada). Uso: python -m tools.gerar_hermes"""
import re
from pathlib import Path

from gabi.mcp.servidor import ESCOPOS_HERMES, ferramentas_do_token

DOC = Path(__file__).resolve().parent.parent / "docs" / "fontes" / "hermes.md"


def lista_atual() -> str:
    return "\n".join(f"      - {n}" for n in ferramentas_do_token(ESCOPOS_HERMES))


if __name__ == "__main__":
    s = DOC.read_text(encoding="utf-8")
    DOC.write_text(re.sub(r"(      include:\n)(?:      - .*\n?)+", lambda m: m.group(1) + lista_atual() + "\n", s), encoding="utf-8")
    print("ok")
