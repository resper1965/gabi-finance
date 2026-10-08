"""Registro de rodadas: cada captura/importação/backup vira uma linha consultável. Consome: db."""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class _Contagens:
    lidos: int = 0
    novos: int = 0
    alterados: int = 0
    aviso: str | None = None  # rodada ok mas incompleta (ex.: uma conta falhou): fica visível em rodada.erro
    id: int = 0


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def registrar_rodada(con: sqlite3.Connection, fonte: str):
    rid = con.execute("insert into rodada(fonte, inicio, status) values (?, ?, 'rodando')",
                      (fonte, _agora())).lastrowid
    r = _Contagens(id=rid)
    try:
        yield r
    except BaseException as e:
        con.execute("update rodada set fim=?, status='erro', erro=?, lidos=?, novos=?, alterados=? where id=?",
                    (_agora(), f"{type(e).__name__}: {e}", r.lidos, r.novos, r.alterados, rid))
        raise
    con.execute("update rodada set fim=?, status='ok', lidos=?, novos=?, alterados=?, erro=? where id=?",
                (_agora(), r.lidos, r.novos, r.alterados, r.aviso, rid))
