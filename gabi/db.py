"""Conexão SQLite (WAL, FKs) e migrações numeradas. Consome: nada. Spec §12/§13.4."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def conectar(caminho: Path) -> sqlite3.Connection:
    # isolation_level=None: transações explícitas (BEGIN/COMMIT) em migrar().
    con = sqlite3.connect(caminho, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("pragma journal_mode=wal")
    con.execute("pragma foreign_keys=on")
    con.execute("pragma busy_timeout=5000")
    return con


def migrar(con: sqlite3.Connection, pasta: Path) -> list[str]:
    con.execute("create table if not exists schema_versao(nome text primary key, aplicada_em text not null)")
    feitas = {r[0] for r in con.execute("select nome from schema_versao")}
    aplicadas = []
    for arq in sorted(Path(pasta).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if arq.name in feitas:
            continue
        con.execute("begin")
        try:
            for instrucao in _instrucoes(arq.read_text(encoding="utf-8")):
                con.execute(instrucao)
            con.execute("insert into schema_versao values (?, ?)",
                        (arq.name, datetime.now(timezone.utc).isoformat()))
            con.execute("commit")
        except BaseException:
            con.execute("rollback")
            raise
        aplicadas.append(arq.name)
    return aplicadas


def _instrucoes(sql: str) -> list[str]:
    """Divide em instruções completas (sqlite3.complete_statement respeita triggers e strings)."""
    saida, atual = [], ""
    for linha in sql.splitlines(keepends=True):
        atual += linha
        if sqlite3.complete_statement(atual):
            if atual.strip():
                saida.append(atual.strip())
            atual = ""
    if atual.strip():
        saida.append(atual.strip())
    return saida
