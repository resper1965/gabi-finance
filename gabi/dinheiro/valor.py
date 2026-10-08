"""Dinheiro em centavos inteiros (R7): nunca float no banco; na API, string decimal "1234.56". Consome: nada."""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_PREFIXO = re.compile(r"^(R\$|BRL)\s*", re.I)


def para_centavos(v: str | int | float | None) -> int | None:
    """Aceita "1.234,56" (BR), "1234.56", "BRL312.45", "R$ -10,00", int e float. Vazio vira None; inválido, ValueError.
    "1.234.567" (vários pontos) é milhar BR; um ponto só é decimal. Arredonda meio-para-cima em centavos."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"valor inválido: {v!r}")
    if isinstance(v, (int, float)):
        return _quantizar(Decimal(str(v)))
    bruto = str(v).strip()
    if not bruto:
        return None
    s = _PREFIXO.sub("", bruto).strip()
    if not s:
        raise ValueError(f"valor inválido (só o símbolo da moeda): {v!r}")
    if "," in s:
        if s.count(",") > 1 or "." in s.split(",")[1]:
            raise ValueError(f"valor inválido: {v!r}")
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        raise ValueError(f"valor inválido: {v!r}")
    return _quantizar(Decimal(s))


def _quantizar(d: Decimal) -> int:
    try:
        return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation as e:
        raise ValueError(f"valor inválido: {d!r}") from e


def formatar(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    inteiro, resto = divmod(abs(centavos), 100)
    return f"{sinal}{inteiro}.{resto:02d}"


def somar(*centavos: int) -> int:
    return sum(centavos)
