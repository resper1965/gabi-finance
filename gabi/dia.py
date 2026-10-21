"""Tela Hoje e resumo da manhã: lê SÓ de tabelas prontas (nenhuma chamada de rede). Consome agenda_evento, email_msg e dinheiro.contas_pagar.
Veio de gabi/trabalho/hoje.py (ADR-023), sem os e-mails do Trabalho legado nem o filtro por empresa/frente."""
import datetime as dt

from gabi.agenda import consulta
from gabi.correio import consulta as consulta_correio
from gabi.dinheiro import contas_pagar as cp
from gabi.dinheiro.valor import formatar


def _dinheiro(con, hoje: dt.date) -> dict:
    g = cp.contas_a_pagar(con, hoje, hoje)
    soma = lambda itens: sum(i["valor_centavos"] or 0 for i in itens)  # noqa: E731
    caixa = cp.caixa_unico(con, hoje)
    return {"saldo": formatar(caixa.saldo_centavos), "atrasadas": {"n": len(g["atrasadas"]), "valor": formatar(soma(g["atrasadas"]))},
            "sai_hoje": formatar(soma(g["hoje"])), "pago_hoje": formatar(soma([i for i in g["pagas"] if (i.get("pago_em") or "")[:10] == hoje.isoformat()]))}


def hoje(con, agora: dt.datetime, *, painel: bool = False) -> dict:
    """`painel=True` só na rota do painel: a política `agenda.privados=so_painel` mascara títulos privados para os demais canais."""
    fuso = consulta.fuso_da_agenda(con)
    dia_agenda = consulta.dia_local(agora, fuso).isoformat()
    correio = consulta_correio.importantes(con, agora=agora)
    prioridades = [{"tipo": "email_emergencial", "titulo": f"{m['remetente'] or '?'} — {m['assunto'] or '(sem assunto)'}", "motivo": m["motivo"], "ref": m["id"]}
                   for m in correio if m["classe"] == "emergencial"]
    prioridades += [{"tipo": "conflito", "titulo": "Conflito na agenda", "ref": c.evento_a, "sugestao": c.sugestao_inicio}
                    for c in consulta.conflitos(con, dia_agenda, dia_agenda, fuso)]
    return {"prioridades": prioridades, "agenda": consulta.agenda_do_dia(con, dia_agenda, fuso, painel=painel), "correio_importantes": correio,
            "dinheiro": _dinheiro(con, agora.date())}
