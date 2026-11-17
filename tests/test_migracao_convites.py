"""Migração 0088: colunas de convite em agenda_evento (a tabela fica no corte do gabi-finance; envio_proposta e seus testes saíram com a 0090)."""
from pathlib import Path

from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent / "migrations"


def _banco(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    return con


def test_agenda_evento_tem_as_tres_colunas(tmp_path):
    con = _banco(tmp_path)
    cols = {r[1] for r in con.execute("pragma table_info(agenda_evento)")}
    assert {"resposta", "organizador_nome", "serie_id"} <= cols
