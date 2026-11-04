"""Migração 0088: convites de agenda (colunas em agenda_evento; envio_proposta aceita convite_resposta sem perder linhas)."""
import shutil
import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent / "migrations"
INS = "insert into envio_proposta(tipo, conta, conteudo, hash, chave, vence_em) values (?, 'c', '{}', 'h', ?, '2026-12-01')"


def _banco(tmp_path):
    con = conectar(tmp_path / "g.db")
    migrar(con, MIGR)
    return con


def test_agenda_evento_tem_as_tres_colunas(tmp_path):
    con = _banco(tmp_path)
    cols = {r[1] for r in con.execute("pragma table_info(agenda_evento)")}
    assert {"resposta", "organizador_nome", "serie_id"} <= cols


def test_envio_proposta_aceita_convite_resposta(tmp_path):
    con = _banco(tmp_path)
    con.execute(INS, ("convite_resposta", "k1"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(INS, ("x", "k2"))


def test_migracao_preserva_propostas_existentes(tmp_path):
    antes = tmp_path / "antes"
    antes.mkdir()
    for arq in sorted(MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if arq.name < "0088":
            shutil.copy(arq, antes / arq.name)
    con = conectar(tmp_path / "g.db")
    migrar(con, antes)
    con.execute(INS, ("evento", "k0"))
    antiga = tuple(con.execute("select * from envio_proposta").fetchone())
    migrar(con, MIGR)
    assert [tuple(r) for r in con.execute("select * from envio_proposta")] == [antiga]
    assert con.execute("select 1 from sqlite_master where type='index' and name='envio_proposta_estado'").fetchone()
