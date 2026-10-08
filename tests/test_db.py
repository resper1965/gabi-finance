import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar


def _pasta(tmp_path, arquivos: dict[str, str]) -> Path:
    p = tmp_path / "migracoes"
    p.mkdir()
    for nome, sql in arquivos.items():
        (p / nome).write_text(sql, encoding="utf-8")
    return p


def test_conectar_usa_wal_e_chaves_estrangeiras(tmp_path):
    con = conectar(tmp_path / "g.db")
    assert con.execute("pragma journal_mode").fetchone()[0] == "wal"
    assert con.execute("pragma foreign_keys").fetchone()[0] == 1
    assert con.execute("pragma busy_timeout").fetchone()[0] == 5000
    assert con.row_factory is sqlite3.Row


def test_migrar_aplica_em_ordem_e_devolve_nomes(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {
        "0002_b.sql": "create table b(x);",
        "0001_a.sql": "create table a(x);",
    })
    assert migrar(con, pasta) == ["0001_a.sql", "0002_b.sql"]
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"a", "b", "schema_versao"} <= nomes


def test_migrar_duas_vezes_nao_reaplica(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {"0001_a.sql": "create table a(x);"})
    migrar(con, pasta)
    assert migrar(con, pasta) == []


def test_migracao_que_falha_desfaz_tudo_e_nao_grava_versao(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {"0001_ruim.sql": "create table ok(x); insert into nao_existe values (1);"})
    with pytest.raises(sqlite3.Error):
        migrar(con, pasta)
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "ok" not in nomes
    assert con.execute("select count(*) from schema_versao").fetchone()[0] == 0


def test_migracao_nova_roda_so_a_nova(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {"0001_a.sql": "create table a(x);"})
    migrar(con, pasta)
    (pasta / "0002_b.sql").write_text("create table b(x);")
    assert migrar(con, pasta) == ["0002_b.sql"]
