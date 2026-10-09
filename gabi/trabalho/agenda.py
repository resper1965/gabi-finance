"""Agenda: grava eventos vindos do Graph/Google (idempotente por caixa + externo_id). Não cria nem altera evento na origem (proposta de horário só sai após confirmação)."""
import json

from gabi.db import transacao


def ingerir_eventos(con, caixa_id: int, fonte) -> int:
    """`fonte(caixa: dict, cursor) -> (eventos, novo_cursor)`; só caixas liberadas (estado 'sim'). Devolve quantos eventos entraram ou mudaram."""
    caixa = con.execute("select * from caixa_email where id=?", (caixa_id,)).fetchone()
    if caixa is None or caixa["estado"] != "sim":
        return 0
    eventos, _ = fonte(dict(caixa), None)
    with transacao(con):
        for e in eventos:
            con.execute("insert into evento(caixa_id, externo_id, inicio, fim, titulo, participantes, link_reuniao) values (?,?,?,?,?,?,?) "
                        "on conflict(caixa_id, externo_id) do update set inicio=excluded.inicio, fim=excluded.fim, titulo=excluded.titulo, "
                        "participantes=excluded.participantes, link_reuniao=excluded.link_reuniao",
                        (caixa_id, e["externo_id"], e["inicio"], e["fim"], e.get("titulo"), json.dumps(e.get("participantes") or []), e.get("link_reuniao")))
    return len(eventos)
