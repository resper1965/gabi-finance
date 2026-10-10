"""Palavras de risco da escuta. A lista é DADO (tabela parametro, chave escuta.palavras_risco, JSON), nunca código."""
import json
import re
import unicodedata

CHAVE = "escuta.palavras_risco"


def _norm(s: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", sem.casefold()))


def palavras_risco(con) -> list[str]:
    linha = con.execute("select valor from parametro where chave=?", (CHAVE,)).fetchone()
    if linha is None:
        return []
    try:
        lista = json.loads(linha[0])
    except (ValueError, TypeError):
        return []
    return [p for p in lista if isinstance(p, str)] if isinstance(lista, list) else []


def tem_risco(texto: str, palavras: list[str]) -> bool:
    """Sem acento, sem caixa, palavra inteira (aceita expressão de várias palavras)."""
    alvo = f" {_norm(texto or '')} "
    return any((n := _norm(p)) and f" {n} " in alvo for p in palavras)
