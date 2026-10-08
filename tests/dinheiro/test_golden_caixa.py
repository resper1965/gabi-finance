"""Prova que as funções puras portadas do finlib reproduzem o gabi-fin (referências sintéticas de tools/golden.py)."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from gabi.dinheiro import caixa
from tools.golden import _ser

GOLDEN = Path(__file__).parent.parent / "golden"


def _chamar(caso):
    fn, a = caso["fn"], list(caso["args"])
    for i in caso.get("data", []):
        a[i] = dt.date.fromisoformat(a[i])
    if fn == "_w_natureza":
        return caixa.natureza(a[0], a[1], a[2], a[3], caixa.dono_tokens(a[4]))
    if fn == "_w_aplica":
        return caixa.aplica_regras(a[0], [(re.compile(p, re.I), c, pes) for p, c, pes in a[1]])
    if fn == "_w_boleto":
        linha = caixa.gera_linha(a[0], a[1], dt.date.fromisoformat(a[2]), a[3])
        if len(a) > 5 and a[5]:
            linha = linha[:-1] + str((int(linha[-1]) + 1) % 10)
        return {"linha": linha, "resultado": caixa.conferir_boleto(linha, dt.date.fromisoformat(a[4]))}
    if fn == "_w_conferir":
        return caixa.conferir_boleto(a[0], dt.date.fromisoformat(a[1]))
    return getattr(caixa, fn)(*a)


PORTADAS = {"norm", "num", "dono_tokens", "meses_atras", "_w_natureza", "_w_aplica", "_w_boleto", "_w_conferir"}
CASOS = [c for c in json.loads((GOLDEN / "finlib.json").read_text(encoding="utf-8")) if c["fn"] in PORTADAS]


def _id(c):
    return f'{c["fn"]}:{json.dumps(c["args"], ensure_ascii=False)[:60]}'


@pytest.mark.parametrize("caso", CASOS, ids=_id)
def test_porte_reproduz_o_gabi_fin(caso):
    assert "saida" in caso
    assert _ser(_chamar(caso)) == caso["saida"]


def test_todas_as_funcoes_portadas_tem_casos():
    assert {c["fn"] for c in CASOS} == PORTADAS
