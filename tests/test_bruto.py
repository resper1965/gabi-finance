import gzip
import json
import stat
from datetime import date

import pytest

from gabi.bruto import gravar_bruto

DIA = date(2026, 10, 8)


def test_bruto_grava_jsonl_gz_legivel(tmp_path):
    p = gravar_bruto(tmp_path, "open-finance", DIA, [{"a": 1}, {"b": 2}])
    assert p == tmp_path / "open-finance" / "2026" / "10" / "08.jsonl.gz"
    linhas = gzip.open(p, "rt", encoding="utf-8").read().splitlines()
    assert [json.loads(l) for l in linhas] == [{"a": 1}, {"b": 2}]


def test_bruto_nao_sobrescreve(tmp_path):
    gravar_bruto(tmp_path, "f", DIA, [{"a": 1}])
    with pytest.raises(FileExistsError):
        gravar_bruto(tmp_path, "f", DIA, [{"a": 2}])
    assert json.loads(gzip.open(tmp_path / "f/2026/10/08.jsonl.gz", "rt").read()) == {"a": 1}


def test_bruto_permissao_600(tmp_path):
    p = gravar_bruto(tmp_path, "f", DIA, [{"a": 1}])
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_bruto_preserva_acentos(tmp_path):
    p = gravar_bruto(tmp_path, "f", DIA, [{"nome": "Açaí da Conceição"}])
    assert json.loads(gzip.open(p, "rt", encoding="utf-8").read())["nome"] == "Açaí da Conceição"


def test_bruto_falha_no_meio_nao_deixa_arquivo_final(tmp_path):
    def linhas():
        yield {"a": 1}
        raise OSError("disco cheio")

    with pytest.raises(OSError):
        gravar_bruto(tmp_path, "f", DIA, linhas())
    assert not (tmp_path / "f/2026/10/08.jsonl.gz").exists()
