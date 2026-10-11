"""Valor de um lançamento em reais, a partir da transação crua do mcp.ai. Função pura, usada pela captura e por tools.corrigir_moeda.

Regra: `amount` está na moeda da compra (`currencyCode`); em compra no exterior, `amountInAccountCurrency` é o valor em REAIS cobrado.
Moeda estrangeira com esse valor numérico: usa-se ele (convertido=True). Sem ele (ausente, vazio, não numérico): grava-se o original
em valor_centavos com convertido=False, e o produtor de avisos conta esses casos. Nunca se estima câmbio. Consome: caixa, valor."""
import math
from typing import NamedTuple

from gabi.dinheiro import caixa
from gabi.dinheiro.valor import para_centavos


class ValorLancamento(NamedTuple):
    centavos: int             # sempre em reais quando convertido
    moeda: str | None         # None = BRL
    original_centavos: int | None  # None em BRL; mesmo sinal de `centavos`
    convertido: bool
    reais: float              # `centavos` como float (para a classificação de natureza)


def _num(v) -> float | None:
    n = caixa.num(v) if v is not None else None
    return n if n is not None and math.isfinite(n) else None


def _sinal(v: float, typ: str, tipo_conta: str) -> float:
    if typ == "DEBIT" and v > 0:
        v = -v
    if tipo_conta == "CREDIT" and typ == "CREDIT" and v < 0:
        v = -v
    return v


def valor_lancamento(t: dict, tipo_conta: str) -> ValorLancamento:
    typ = str(t.get("type", "")).upper()
    original = _sinal(_num(t.get("amount")) or 0, typ, tipo_conta)
    moeda = str(t.get("currencyCode") or "").strip().upper() or None
    if moeda in (None, "BRL"):
        c = para_centavos(round(original, 2))
        return ValorLancamento(c, None, None, True, original)
    em_reais = _num(t.get("amountInAccountCurrency"))
    orig_c = para_centavos(round(original, 2))
    if em_reais is None:
        return ValorLancamento(orig_c, moeda, orig_c, False, original)
    reais = _sinal(em_reais, typ, tipo_conta)
    return ValorLancamento(para_centavos(round(reais, 2)), moeda, orig_c, True, reais)
