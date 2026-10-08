import json
from pathlib import Path

import pytest

from gabi.dinheiro import emissores
from tools.golden import _ser

CASOS = json.loads((Path(__file__).parent.parent / "golden" / "emissores.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: f'{c["fn"]}:{c["args"]}')
def test_emissores_reproduz_o_gabi_fin(caso):
    assert _ser(getattr(emissores, caso["fn"])(*caso["args"])) == caso["saida"]
