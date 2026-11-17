"""Cadastro de quem pode acessar (login Tailscale -> pessoa + nível). Uso: python -m gabi.acesso adicionar|listar."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.identidade import NIVEIS, normalizar_login

MIGRACOES = Path(__file__).resolve().parent.parent / "migrations"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def adicionar(con: sqlite3.Connection, login: str, pessoa_id: str, nivel: str, por: str) -> None:
    if nivel not in NIVEIS:
        raise ValueError(f"nível inválido: {nivel!r} (use {', '.join(NIVEIS)})")
    login = normalizar_login(login)
    con.execute("insert into acesso(login, pessoa_id, nivel, criado_em) values (?,?,?,?) "
                "on conflict(login) do update set pessoa_id=excluded.pessoa_id, nivel=excluded.nivel",
                (login, pessoa_id, nivel, _agora()))
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)",
                (_agora(), por, f"acesso: {login} -> {pessoa_id} ({nivel})", "gabi.acesso"))


def listar(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute("select login, pessoa_id, nivel, criado_em from acesso order by login")]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="gabi.acesso")
    ap.add_argument("--banco", default="/var/lib/gabi-finance/gabi.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("adicionar")
    a.add_argument("login"); a.add_argument("pessoa_id"); a.add_argument("nivel")
    sub.add_parser("listar")
    args = ap.parse_args()
    con = conectar(Path(args.banco))
    migrar(con, MIGRACOES)
    if args.cmd == "adicionar":
        adicionar(con, args.login, args.pessoa_id, args.nivel, por="cli")
        print(f"ok: {normalizar_login(args.login)} -> {args.pessoa_id} ({args.nivel})")
    else:
        for l in listar(con):
            print(f"{l['login']:40} {l['pessoa_id'] or '-':12} {l['nivel']}")
    sys.exit(0)
