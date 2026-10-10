"""Condição opcional de uma regra: só vale se o lançamento também confere em conta, faixa de valor e/ou dia da semana.
JSON: {"conta_id": [1, 2], "valor_min": 1000, "valor_max": 5000, "dias_semana": [5, 6]}. Valor em centavos, absoluto (entrada e saída); 0 = segunda … 6 = domingo.
Todas as chaves presentes precisam conferir. Consome: nada (puro)."""
import datetime as dt

CHAVES = {"conta_id", "valor_min", "valor_max", "dias_semana"}


def _inteiros(v, nome: str, minimo: int | None = None, maximo: int | None = None) -> list[int]:
    lista = v if isinstance(v, list) else [v] if isinstance(v, int) and not isinstance(v, bool) else None
    if not lista or any(not isinstance(i, int) or isinstance(i, bool) or (minimo is not None and i < minimo) or (maximo is not None and i > maximo) for i in lista):
        raise ValueError(f"condição: {nome} inválido")
    return sorted(set(lista))


def validar(cond) -> dict | None:
    """Normaliza (lista de inteiros, sem repetição) ou levanta ValueError. Vazio/None = sem condição."""
    if cond is None or cond == {}:
        return None
    if not isinstance(cond, dict) or set(cond) - CHAVES:
        raise ValueError(f"condição com campos desconhecidos ou formato inválido (aceita: {sorted(CHAVES)})")
    saida = {}
    if "conta_id" in cond:
        saida["conta_id"] = _inteiros(cond["conta_id"], "conta_id", 1)
    if "dias_semana" in cond:
        saida["dias_semana"] = _inteiros(cond["dias_semana"], "dias_semana", 0, 6)
    for k in ("valor_min", "valor_max"):
        if k in cond:
            if not isinstance(cond[k], int) or isinstance(cond[k], bool) or cond[k] < 0:
                raise ValueError(f"condição: {k} inválido")
            saida[k] = cond[k]
    if "valor_min" in saida and "valor_max" in saida and saida["valor_min"] > saida["valor_max"]:
        raise ValueError("condição: valor_min maior que valor_max")
    return saida


def confere(cond: dict | None, lancamento) -> bool:
    if not cond:
        return True
    if "conta_id" in cond and lancamento["conta_id"] not in cond["conta_id"]:
        return False
    v = abs(lancamento["valor_centavos"] or 0)
    if v < cond.get("valor_min", 0) or ("valor_max" in cond and v > cond["valor_max"]):
        return False
    if "dias_semana" in cond and dt.date.fromisoformat(lancamento["data"][:10]).weekday() not in cond["dias_semana"]:
        return False
    return True
