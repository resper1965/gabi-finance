import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_migracao_tipo_e_dispensado(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('x','X','X','dia:5')")
    assert con.execute("select tipo from compromisso_linha where id='x'").fetchone()[0] == "fixa"
    con.execute("insert into valor_do_mes(mes, compromisso, tipo) values ('2026-10','x','dispensado')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update compromisso_linha set tipo='outra' where id='x'")
