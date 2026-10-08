"""Feriados nacionais e dia útil, portados do gabi-fin/previstas.py SEM alterar a lógica.

Provado contra tests/golden/previstas.json. O resto do previstas (contas previstas pelo extrato) entra na T1.7. Consome: nada.
"""
import re
import unicodedata
from datetime import date


def forma(desc):
    """Como o Boss paga, pela descricao do extrato (sem cadastro)."""
    s = "".join(c for c in unicodedata.normalize("NFKD", (desc or "").upper()) if not unicodedata.combining(c))
    if re.search(r"\b(PIX|TED|DOC|TRANSF)", s):
        return "transferência"
    if re.search(r"DEBITO\s+AUTOMATICO|\bDEB\.?\s*AUT", s):
        return "débito automático"
    if "BOLETO" in s:
        return "boleto (DDA)"
    return None


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados(ano):
    """Feriados nacionais (bancos fechados): fixos + carnaval (seg e ter), sexta-feira santa e Corpus Christi."""
    from datetime import timedelta
    p = _pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
    return {date(ano, m, d) for m, d in fixos} | {p - timedelta(days=48), p - timedelta(days=47),
                                                  p - timedelta(days=2), p + timedelta(days=60)}


def dia_util(ano, mes, n):
    """n-esimo dia util do mes."""
    fer, d, conta = feriados(ano), date(ano, mes, 1), 0
    while True:
        if d.weekday() < 5 and d not in fer:
            conta += 1
            if conta == n:
                return d
        d = date.fromordinal(d.toordinal() + 1)
