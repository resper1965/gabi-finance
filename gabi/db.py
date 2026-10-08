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
    aplicadas = []
    for arq in sorted(Path(pasta).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        con.execute("begin immediate")  # lock de escrita já aqui: dois processos migrando não se atropelam
        try:
            if con.execute("select 1 from schema_versao where nome=?", (arq.name,)).fetchone():
                con.execute("commit")  # outro processo já aplicou
                continue
            for instrucao in _instrucoes(arq.read_text(encoding="utf-8")):
                con.execute(instrucao)
            con.execute("insert into schema_versao values (?, ?)",
                        (arq.name, datetime.now(timezone.utc).isoformat()))
            con.execute("commit")
        except BaseException:
            if con.in_transaction:
                con.execute("rollback")
            raise
        aplicadas.append(arq.name)
    return aplicadas


def _instrucoes(sql: str) -> list[str]:
    """Divide em instruções completas, mesmo várias na mesma linha. complete_statement respeita triggers e strings."""
    saida, inicio = [], 0
    for i, c in enumerate(sql):
        if c == ";" and sqlite3.complete_statement(sql[inicio:i + 1]):
            trecho = sql[inicio:i + 1].strip()
            if trecho:
                saida.append(trecho)
            inicio = i + 1
    resto = sql[inicio:].strip()
    if resto:
        saida.append(resto)
    return saida
