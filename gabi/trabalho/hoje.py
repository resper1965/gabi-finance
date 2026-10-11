"""Tela Hoje: lê SÓ de tabelas prontas (nenhuma chamada de rede no caminho da requisição). Consome item_email, agenda_evento, tarefa, frente e dinheiro.contas_pagar.
Filtro: 'all', um id de empresa, ou 't-<id da frente>'. Com filtro, e-mails e agenda são recortados; o bloco `dinheiro` só vai em 'all' (compromisso não tem frente)."""
import datetime as dt

from gabi.agenda import consulta
from gabi.correio import consulta as consulta_correio
from gabi.dinheiro import contas_pagar as cp
from gabi.dinheiro.valor import formatar

LIMITE_EMAILS = 10


def _recorte_email(filtro: str) -> tuple[str, list]:
    if filtro == "all":
        return "", []
    if filtro.startswith("t-"):
        return " and i.id in (select ref_id from item_frente where frente_id=? and tipo='email' and estado='confirmado')", [int(filtro[2:])]
    return " and c.empresa_id=?", [filtro]


def emails_importantes(con, filtro: str = "all", limite: int = LIMITE_EMAILS) -> list[dict]:
    sql, args = _recorte_email(filtro)
    return [dict(r) for r in con.execute(
        "select i.id, i.remetente, i.assunto, i.recebido_em, i.motivo, i.frente_id, c.endereco as caixa from item_email i join caixa_email c on c.id=i.caixa_id "
        f"where i.relevante=1 and i.estado='novo'{sql} order by i.recebido_em desc limit ?", [*args, limite])]


def _dinheiro(con, hoje: dt.date) -> dict:
    g = cp.contas_a_pagar(con, hoje, hoje)
    soma = lambda itens: sum(i["valor_centavos"] or 0 for i in itens)  # noqa: E731
    caixa = cp.caixa_unico(con, hoje)
    return {"saldo": formatar(caixa.saldo_centavos), "atrasadas": {"n": len(g["atrasadas"]), "valor": formatar(soma(g["atrasadas"]))},
            "sai_hoje": formatar(soma(g["hoje"])), "pago_hoje": formatar(soma([i for i in g["pagas"] if (i.get("pago_em") or "")[:10] == hoje.isoformat()])),
            "nibo": None}  # sem backend até a Fase 2 aceitar o Nibo com dado real


def hoje(con, agora: dt.datetime, filtro: str = "all", *, painel: bool = False) -> dict:
    """`painel=True` só na rota do painel: a política `agenda.privados=so_painel` mascara títulos privados para os demais canais."""
    dia = agora.date()
    fuso = consulta.fuso_da_agenda(con)
    dia_agenda = consulta.dia_local(agora, fuso).isoformat()
    mails = emails_importantes(con, filtro)
    # compromisso não tem empresa nem frente: a agenda (e os conflitos) só vão no 'all'
    agenda = consulta.agenda_do_dia(con, dia_agenda, fuso, painel=painel) if filtro == "all" else []
    correio = consulta_correio.importantes(con, agora=agora) if filtro == "all" else []  # caixa de e-mail não tem empresa nem frente: só no 'all'
    prioridades = [{"tipo": "email_emergencial", "titulo": f"{m['remetente'] or '?'} — {m['assunto'] or '(sem assunto)'}", "motivo": m["motivo"], "ref": m["id"]}
                   for m in correio if m["classe"] == "emergencial"]
    prioridades += [{"tipo": "email", "titulo": m["assunto"], "motivo": m["motivo"], "ref": m["id"]} for m in mails[:3]]
    prioridades += [{"tipo": "conflito", "titulo": "Conflito na agenda", "ref": c.evento_a, "sugestao": c.sugestao_inicio}
                    for c in consulta.conflitos(con, dia_agenda, dia_agenda, fuso)] if filtro == "all" else []
    return {"filtro": filtro, "prioridades": prioridades, "agenda": agenda, "emails_importantes": mails, "correio_importantes": correio,
            "dinheiro": _dinheiro(con, dia) if filtro == "all" else None}
