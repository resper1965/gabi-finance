import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.dinheiro import planilha
from tools.golden import _ser

CASOS = json.loads((Path(__file__).parent.parent / "golden" / "planilha.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["args"][0])
def test_validar_reproduz_o_gabi_fin(caso):
    s = caso["saida"]
    assert _ser(planilha.validar(s["bruto"], dt.date(2026, 10, 8))) == s["leitura"]


def test_cobre_linhas_validas_invalidas_e_series_sobrepostas():
    completa = next(c for c in CASOS if c["args"][0] == "completa")["saida"]["leitura"]
    motivos = " | ".join(i["motivo"] for i in completa["invalidas"])
    for trecho in ("vencimento", "forma", "id", "repetido", "nome vazio", "valido_de depois", "sobrepõe", "não é número",
                   "inexistente", "não é AAAA-MM"):
        assert trecho in motivos, trecho
    assert [l["id"] for l in completa["linhas"]] == ["aluguel", "energia", "escola"]
