import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.cobrar import extrator
from tools.golden import _ser

CASOS = json.loads((Path(__file__).parent.parent / "golden" / "extrator.json").read_text(encoding="utf-8"))


def _args(caso):
    a = list(caso["args"])
    for i in caso.get("data", []):  # índices que o gabi-fin recebe como date (o golden guarda ISO)
        a[i] = dt.date.fromisoformat(a[i])
    return a


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: f'{c["fn"]}:{str(c["args"])[:60]}')
def test_porte_reproduz_o_gabi_fin(caso):
    assert _ser(getattr(extrator, caso["fn"])(*_args(caso))) == caso["saida"]


def test_cobre_as_seis_funcoes_portadas():
    assert {c["fn"] for c in CASOS} == {"pix_valido", "pix_valor", "achar_codigo", "achar_cnpj", "tipo_documento", "ler_comprovante_pix"}
