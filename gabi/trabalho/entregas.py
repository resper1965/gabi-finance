"""Entregas (Linear, só leitura): espelho local das issues abertas; as que saíram da lista (concluídas/canceladas) são removidas do espelho."""
from gabi.db import transacao


def ingerir_entregas(con, entregas: list[dict]) -> int:
    with transacao(con):
        for e in entregas:
            con.execute("insert into entrega(externo_id, identificador, titulo, projeto, responsavel, prazo, estado, atualizado_em) values (?,?,?,?,?,?,?,?) "
                        "on conflict(externo_id) do update set identificador=excluded.identificador, titulo=excluded.titulo, projeto=excluded.projeto, "
                        "responsavel=excluded.responsavel, prazo=excluded.prazo, estado=excluded.estado, atualizado_em=excluded.atualizado_em",
                        (e["externo_id"], e["identificador"], e["titulo"], e.get("projeto"), e.get("responsavel"), e.get("prazo"), e["estado"], e.get("atualizado_em")))
        ids = [e["externo_id"] for e in entregas]
        con.execute(f"delete from entrega where externo_id not in ({','.join('?' * len(ids))})" if ids else "delete from entrega", ids)
    return len(entregas)
