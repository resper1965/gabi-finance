"""Valor de um lançamento em reais, a partir da transação crua do mcp.ai. Função pura, usada pela captura e por tools.corrigir_moeda.

Regra: `amount` está na moeda da compra (`currencyCode`); em compra no exterior, `amountInAccountCurrency` é o valor em REAIS cobrado.
Moeda estrangeira com esse valor numérico: usa-se ele (convertido=True). Sem ele (ausente, vazio, não numérico): grava-se o original
em valor_centavos com convertido=False, e o produtor de avisos conta esses casos. Nunca se estima câmbio. Consome: caixa, valor."""
from typing import NamedTuple

from gabi.dinheiro.valor import para_centavos


class ValorIlegivel(ValueError):
    """`amount` ausente, vazio ou não numérico: o lançamento não tem valor confiável e não pode virar R$ 0,00."""


class ValorLancamento(NamedTuple):
    centavos: int             # sempre em reais quando convertido
    moeda: str | None         # None = BRL
    original_centavos: int | None  # None em BRL; mesmo sinal de `centavos`
    convertido: bool
    reais: float              # `centavos` como float (para a classificação de natureza)


def _centavos(v) -> int | None:
    """Centavos a partir do texto/número (meio-para-cima, sem passar por float); vazio, não numérico, nan e inf viram None."""
    try:
        return para_centavos(v if isinstance(v, (int, float)) else str(v).strip().replace(" ", "")) if v is not None else None
    except (ValueError, ArithmeticError):
        return None


def _sinal(c: int, typ: str, tipo_conta: str) -> int:
    if typ == "DEBIT" and c > 0:
        c = -c
    if tipo_conta == "CREDIT" and typ == "CREDIT" and c < 0:
        c = -c
    return c


def valor_lancamento(t: dict, tipo_conta: str) -> ValorLancamento:
    typ = str(t.get("type", "")).upper()
    bruto = _centavos(t.get("amount"))
    if bruto is None:
        raise ValorIlegivel("amount ilegível")
    original = _sinal(bruto, typ, tipo_conta)
    moeda = str(t.get("currencyCode") or "").strip().upper() or None
    if moeda in (None, "BRL"):
        return ValorLancamento(original, None, None, True, original / 100)
    em_reais = _centavos(t.get("amountInAccountCurrency"))
    if em_reais is None or (em_reais == 0 and original != 0):  # ausente, inválido ou zero: não vira R$ 0,00
        return ValorLancamento(original, moeda, original, False, original / 100)
    # grandeza vem do valor em reais; o sinal, do original já normalizado (as duas colunas sempre têm o mesmo sinal)
    reais = abs(em_reais) if original > 0 else -abs(em_reais) if original < 0 else _sinal(em_reais, typ, tipo_conta)
    return ValorLancamento(reais, moeda, original, True, reais / 100)
