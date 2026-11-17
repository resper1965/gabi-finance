"""Chaves de agentes externos do MCP (ADR-036): regras por cima de gabi/mcp/tokens.py. O segredo só sai em criar/rotacionar, uma vez; nada aqui devolve hash."""
import contextlib
import datetime as dt
import sqlite3

from gabi.avisos import _parametro
from gabi.mcp import tokens
from gabi.mcp.servidor import ESCOPOS_HERMES
from gabi.mcp.tokens import ESCOPOS

UTC = dt.timezone.utc
URL_PADRAO = "https://gabi-finance.tail985643.ts.net:8443/mcp"
ORIGEM = "agentes"


@contextlib.contextmanager
def _transacao(con: sqlite3.Connection):
    """Tudo ou nada. A conexão é autocommit (isolation_level=None), então `with con:` não basta."""
    if con.in_transaction:  # já dentro de uma transação de quem chamou: ela decide o commit
        yield
        return
    con.execute("begin immediate")  # escrita lê antes de gravar: evita SQLITE_BUSY_SNAPSHOT
    try:
        yield
    except BaseException:
        con.execute("rollback")
        raise
    con.execute("commit")


def _auditar(con, agora: dt.datetime, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)", (agora.astimezone(UTC).isoformat(), quem, o_que, ORIGEM))


def _lista(escopos) -> str:
    return ",".join(sorted(set(escopos)))


def listar_agentes(con, agora: dt.datetime) -> list[dict]:
    desde = (agora.astimezone(UTC) - dt.timedelta(days=7)).isoformat()
    uso = {r["token_id"]: (r["ultimo"], r["n7"]) for r in con.execute(
        "select token_id, max(quando) ultimo, sum(quando >= ?) n7 from chamada_mcp where token_id is not null group by token_id", (desde,))}
    out = []
    for t in tokens.listar(con):
        ultimo, n7 = uso.get(t["id"], (None, 0))
        out.append({**t, "ultimo_uso": ultimo, "chamadas_7d": int(n7 or 0)})
    return out


def _item(con, agora, token_id: int) -> dict:
    for a in listar_agentes(con, agora):
        if a["id"] == token_id:
            return a
    raise LookupError(f"token {token_id} não existe")


def _nome(con, token_id: int) -> str:
    r = con.execute("select nome from token_agente where id=?", (token_id,)).fetchone()
    if r is None:
        raise LookupError(f"token {token_id} não existe")
    return r["nome"]


def criar(con, agora: dt.datetime, quem: str, nome: str, escopos: list[str] | None = None) -> dict:
    escopos = list(ESCOPOS_HERMES) if escopos is None else escopos
    with _transacao(con):
        chave = tokens.emitir(con, nome, escopos)
        novo = con.execute("select id, nome, escopo from token_agente where hash=?", (tokens._hash(chave),)).fetchone()
        _auditar(con, agora, quem, f'agente {novo["id"]} "{novo["nome"]}": emitida|escopos={novo["escopo"]}')
    return {"id": novo["id"], "nome": novo["nome"], "escopos": novo["escopo"].split(","), "chave": chave}


def trocar_escopos(con, agora: dt.datetime, quem: str, token_id: int, escopos: list[str]) -> dict:
    with _transacao(con):
        tokens.definir_escopos(con, token_id, escopos)
        _auditar(con, agora, quem, f'agente {token_id} "{_nome(con, token_id)}": escopos={_lista(escopos)}')
    return _item(con, agora, token_id)


def revogar_agente(con, agora: dt.datetime, quem: str, token_id: int) -> dict:
    with _transacao(con):
        nome = _nome(con, token_id)
        tokens.revogar(con, token_id)
        _auditar(con, agora, quem, f'agente {token_id} "{nome}": revogada')
    return _item(con, agora, token_id)


def rotacionar(con, agora: dt.datetime, quem: str, token_id: int) -> dict:
    """Emite uma chave nova com o mesmo nome e escopos e revoga a antiga, na mesma transação (se emitir falha, a antiga segue ativa)."""
    with _transacao(con):
        r = con.execute("select nome, escopo from token_agente where id=? and revogado_em is null", (token_id,)).fetchone()
        if r is None:
            raise LookupError(f"token {token_id} não existe ou foi revogado")
        chave = tokens.emitir(con, r["nome"], r["escopo"].split(","))
        novo = con.execute("select id, nome, escopo from token_agente where hash=?", (tokens._hash(chave),)).fetchone()
        tokens.revogar(con, token_id)
        _auditar(con, agora, quem, f'agente {token_id} "{r["nome"]}": rotacionada (nova {novo["id"]})')
    return {"id": novo["id"], "nome": novo["nome"], "escopos": novo["escopo"].split(","), "chave": chave}


def chamadas(con, token_id: int, limite: int = 50) -> list[dict]:
    _nome(con, token_id)
    return [{"quando": r["quando"], "ferramenta": r["ferramenta"], "status": r["status"]} for r in con.execute(
        "select quando, ferramenta, status from chamada_mcp where token_id=? order by quando desc, id desc limit ?", (token_id, limite))]


def conexao(con) -> dict:
    url = _parametro(con, "mcp.url", URL_PADRAO)
    url = url if isinstance(url, str) and url.strip() else URL_PADRAO
    return {"url": url, "escopos_padrao": list(ESCOPOS_HERMES), "escopos_validos": sorted(ESCOPOS)}
