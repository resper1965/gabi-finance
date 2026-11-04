"""Acelera a suíte: o banco com TODAS as migrações é montado uma vez por processo e copiado (API de backup do SQLite) para cada banco novo.
Só vale para banco vazio com a pasta de migrações do repositório; qualquer outra pasta (testes de migração parcial) segue pelo `migrar` de verdade.
O patch é feito aqui, na importação do conftest, antes de qualquer teste importar `migrar` por nome."""
import sqlite3
from pathlib import Path

import gabi.db as _db

_REAL = _db.migrar
_MIGRACOES = (Path(__file__).resolve().parent.parent / "migrations").resolve()
_modelo: dict = {}


def _banco_modelo():
    if not _modelo:
        base = sqlite3.connect(":memory:", isolation_level=None)
        base.row_factory = sqlite3.Row
        _modelo["con"] = base
        _modelo["nomes"] = _REAL(base, _MIGRACOES)
    return _modelo


def _migrar_rapido(con, pasta):
    vazio = con.execute("select count(*) from sqlite_master").fetchone()[0] == 0
    if vazio and Path(pasta).resolve() == _MIGRACOES:
        m = _banco_modelo()
        m["con"].backup(con)
        return list(m["nomes"])
    return _REAL(con, pasta)


_db.migrar = _migrar_rapido


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_espera_de_retry(monkeypatch):
    """O retry de leitura (2 s, 5 s) nunca dorme de verdade nos testes; quem testa a espera injeta `dorme`."""
    from gabi.fontes import _http
    monkeypatch.setattr(_http, "dormir", lambda s: None)
