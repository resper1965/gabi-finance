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
    pasta = _pasta(tmp_path, {"0001_ruim.sql": "create table ok(x);\ninsert into nao_existe values (1);"})
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


def test_duas_instrucoes_na_mesma_linha_funcionam(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {"0001_a.sql": "create table a(x); create table b(x); insert into a values (1);"})
    assert migrar(con, pasta) == ["0001_a.sql"]
    assert con.execute("select count(*) from a").fetchone()[0] == 1


def test_migracao_com_duas_instrucoes_na_mesma_linha_que_falha_desfaz_tudo(tmp_path):
    con = conectar(tmp_path / "g.db")
    pasta = _pasta(tmp_path, {"0001_ruim.sql": "create table ok(x); insert into nao_existe values (1);"})
    with pytest.raises(sqlite3.Error):
        migrar(con, pasta)
    assert "ok" not in {r[0] for r in con.execute("select name from sqlite_master where type='table'")}


def test_trigger_com_ponto_e_virgula_interno_e_string_com_ponto_e_virgula(tmp_path):
    con = conectar(tmp_path / "g.db")
    sql = ("create table t(x); create table log(m);\n"
           "create trigger tg after insert on t begin insert into log values ('a;b'); insert into log values ('c'); end;\n"
           "insert into t values (1);")
    migrar(con, _pasta(tmp_path, {"0001_a.sql": sql}))
    assert con.execute("select count(*) from log").fetchone()[0] == 2


def test_migrar_concorrente_nao_reaplica_nem_quebra(tmp_path):
    import threading
    banco = tmp_path / "g.db"
    pasta = _pasta(tmp_path, {"0001_a.sql": "create table a(x);", "0002_b.sql": "create table b(x);"})
    resultados, erros = [], []

    def rodar():
        try:
            resultados.append(migrar(conectar(banco), pasta))
        except BaseException as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=rodar) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert erros == []
    assert sorted(len(r) for r in resultados) == [0, 0, 0, 2]  # exatamente um aplicou
    assert conectar(banco).execute("select count(*) from schema_versao").fetchone()[0] == 2


def test_conectar_simultaneo_em_banco_novo_nao_falha_ao_ativar_wal(tmp_path):
    """Ativar o WAL exige um lock que o SQLite não espera pelo busy_timeout: várias conexões novas ao mesmo tempo
    (API subindo + backup + CLI) não podem derrubar umas às outras."""
    import threading
    erros = []
    for rodada in range(10):
        banco = tmp_path / f"g{rodada}.db"
        largada = threading.Barrier(8)

        def abrir():
            largada.wait()
            try:
                conectar(banco).close()
            except BaseException as e:  # noqa: BLE001
                erros.append(e)

        ts = [threading.Thread(target=abrir) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    assert erros == []
