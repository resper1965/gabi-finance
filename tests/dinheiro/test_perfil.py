import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.perfil import perfil
from gabi.dinheiro.repositorio import FonteAnalise

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','Itau','BANK','Itaú','sim')")
    return c


def lanc(con, desc, valor, data, i):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                "values (1,?,?,?,?,'caixa+custo','posted')", (f"{desc}{i}", data, valor, desc))


def classes(con):
    return {p["descricao"]: p["classe"] for p in perfil(FonteAnalise(con, so_liberadas=True), HOJE)}


def test_fixa_todo_mes_no_mesmo_dia_e_regular(con):
    for i, m in enumerate(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]):
        lanc(con, "PIX CLIENTE FIXO", 1000000, f"{m}-07", i)
    assert classes(con)["PIX CLIENTE FIXO"] == "regular"


def test_valor_que_oscila_e_semi(con):
    for i, (m, v) in enumerate(zip(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"], [100000, 190000, 90000, 200000, 110000])):
        lanc(con, "PIX VARIAVEL", v, f"{m}-07", i)
    assert classes(con)["PIX VARIAVEL"] == "semi"


def test_presente_so_em_parte_dos_meses_e_irregular(con):
    for i, m in enumerate(["2026-06", "2026-08", "2026-09"]):  # 3 de 5 meses: ainda é recorrente, mas falha em 40%
        lanc(con, "PIX AVULSO", -50000, f"{m}-07", i)
    r = [p for p in perfil(FonteAnalise(con, so_liberadas=True), HOJE) if p["descricao"] == "PIX AVULSO"]
    assert [p["classe"] for p in r] == ["irregular"] and r[0]["meses_presentes"] == 3 and r[0]["meses_janela"] == 4
