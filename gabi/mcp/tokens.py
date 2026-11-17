"""Tokens de agentes do MCP: o token aparece UMA vez (ao emitir); o banco guarda só o SHA-256. Escopos limitam as ferramentas.

Uso: python -m gabi.mcp.tokens emitir <nome> <escopo,escopo> | escopos <id> <escopo,escopo> | listar | revogar <id>   (Ricardo cola o token no agente).
"""
import hashlib
import secrets
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ESCOPOS = {"fin", "trabalho", "pedidos", "propostas", "decisoes", "sensivel"}  # docs, envios, familia, contatos, atividades e projetos saíram com as ferramentas deles (corte); token antigo com esses escopos continua válido


@dataclass(frozen=True)
class Token:
    id: int
    nome: str
    escopos: frozenset


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def emitir(con: sqlite3.Connection, nome: str, escopos: list[str]) -> str:
    if not nome or not nome.strip():
        raise ValueError("o token precisa de um nome")
    if not escopos or set(escopos) - ESCOPOS:
        raise ValueError(f"escopos válidos: {sorted(ESCOPOS)}")
    token = "gb_" + secrets.token_urlsafe(32)
    con.execute("insert into token_agente(nome, escopo, hash, criado_em) values (?,?,?,?)",
                (nome.strip(), ",".join(sorted(set(escopos))), _hash(token), datetime.now(timezone.utc).isoformat()))
    return token


def validar(con: sqlite3.Connection, token: str | None) -> Token | None:
    if not token or not isinstance(token, str):
        return None
    r = con.execute("select id, nome, escopo from token_agente where hash=? and revogado_em is null", (_hash(token),)).fetchone()
    return Token(r["id"], r["nome"], frozenset(r["escopo"].split(","))) if r else None


def revogar(con: sqlite3.Connection, token_id: int) -> None:
    if con.execute("select 1 from token_agente where id=?", (token_id,)).fetchone() is None:
        raise LookupError(f"token {token_id} não existe")
    con.execute("update token_agente set revogado_em=coalesce(revogado_em, ?) where id=?", (datetime.now(timezone.utc).isoformat(), token_id))


def definir_escopos(con: sqlite3.Connection, token_id: int, escopos: list[str]) -> None:
    """Troca só os escopos de um token ativo; o segredo e o hash não mudam."""
    if not escopos or set(escopos) - ESCOPOS:
        raise ValueError(f"escopos válidos: {sorted(ESCOPOS)}")
    if con.execute("select 1 from token_agente where id=? and revogado_em is null", (token_id,)).fetchone() is None:
        raise LookupError(f"token {token_id} não existe ou foi revogado")
    con.execute("update token_agente set escopo=? where id=?", (",".join(sorted(set(escopos))), token_id))


def listar(con: sqlite3.Connection) -> list[dict]:
    return [{"id": r["id"], "nome": r["nome"], "escopos": r["escopo"].split(","), "criado_em": r["criado_em"],
             "revogado_em": r["revogado_em"], "ativo": r["revogado_em"] is None} for r in con.execute("select * from token_agente order by id")]


if __name__ == "__main__":
    import argparse
    from gabi.db import conectar, migrar
    ap = argparse.ArgumentParser(prog="gabi.mcp.tokens")
    ap.add_argument("--banco", default="/var/lib/gabi-finance/gabi.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emitir"); e.add_argument("nome"); e.add_argument("escopos", help="separados por vírgula: " + ",".join(sorted(ESCOPOS)))
    d = sub.add_parser("escopos"); d.add_argument("id", type=int); d.add_argument("escopos", help="separados por vírgula: " + ",".join(sorted(ESCOPOS)))
    sub.add_parser("listar")
    r = sub.add_parser("revogar"); r.add_argument("id", type=int)
    a = ap.parse_args()
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    if a.cmd == "emitir":
        print("Token (aparece só agora; cole no agente):\n" + emitir(con, a.nome, [x.strip() for x in a.escopos.split(",")]))
    elif a.cmd == "escopos":
        definir_escopos(con, a.id, [x.strip() for x in a.escopos.split(",")])
        print(f"token {a.id}: escopos trocados")
    elif a.cmd == "listar":
        for t in listar(con):
            print(f"{t['id']:>3} {t['nome']:20} {','.join(t['escopos']):30} {'ativo' if t['ativo'] else 'revogado'}")
    else:
        revogar(con, a.id)
        print(f"token {a.id} revogado")
    sys.exit(0)
