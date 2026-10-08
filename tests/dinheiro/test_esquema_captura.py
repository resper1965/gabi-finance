import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo) values ('c1','C6','BANK')")
    return c


def test_0003_adiciona_colunas_de_captura(con):
    lanc = {r["name"] for r in con.execute("pragma table_info(lancamento)")}
    conta = {r["name"] for r in con.execute("pragma table_info(conta)")}
    assert {"natureza", "operacao"} <= lanc
    assert {"titular", "limite_centavos", "disponivel_centavos", "vencimento_fatura"} <= conta


@pytest.mark.parametrize("nat", ["caixa+custo", "caixa", "custo", "neutro", None])
def test_natureza_valida(con, nat):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, natureza) values (1, ?, '2026-10-08', 1, ?)",
                (f"l-{nat}", nat))


def test_natureza_invalida_rejeitada(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, natureza) values (1,'x','2026-10-08',1,'talvez')")


def test_limites_do_cartao_sao_inteiros(con):
    con.execute("update conta set limite_centavos=500000, disponivel_centavos=420000, vencimento_fatura='2026-10-20' where id=1")
    assert con.execute("select typeof(limite_centavos) from conta").fetchone()[0] == "integer"
