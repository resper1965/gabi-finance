import json
from pathlib import Path

import pytest

from gabi.dinheiro import previstas
from tools.golden import _ser

CASOS = json.loads((Path(__file__).parent.parent / "golden" / "previstas.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: f'{c["fn"]}:{c["args"]}')
def test_porte_reproduz_o_gabi_fin(caso):
    assert _ser(getattr(previstas, caso["fn"])(*caso["args"])) == caso["saida"]


def test_cobre_as_quatro_funcoes_portadas():
    assert {c["fn"] for c in CASOS} == {"feriados", "dia_util", "forma"}
