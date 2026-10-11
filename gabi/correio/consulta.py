"""Leitura do correio (`email_msg`) para as superfícies: Hoje, resumo da manhã, MCP `email_listar`, painel (spec 2026-10-11-email-design, §3.7).
Só lê. Só fontes liberadas; nunca o que está na lixeira nem o que o modelo chamou de lixo. Assunto, remetente e trecho só saem pelos canais do dono."""
import datetime as dt

CAMPOS = "m.id, f.conta, m.remetente, m.assunto, m.recebida_em, m.classe, m.prioridade, m.motivo"
_ORDEM = "case m.classe when 'emergencial' then 0 else 1 end, coalesce(m.prioridade, 0) desc, m.recebida_em desc, m.id desc"


def _utc(agora) -> dt.datetime:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    return agora if agora.tzinfo else agora.replace(tzinfo=dt.timezone.utc)


def importantes(con, limite: int = 10) -> list[dict]:
    """Emergenciais e importantes ainda em aberto (classificadas ou alertadas): o emergencial primeiro, depois prioridade e data."""
    return [dict(r) for r in con.execute(
        f"select {CAMPOS} from email_msg m join email_fonte f on f.id=m.fonte_id "
        f"where f.estado='sim' and m.estado in ('classificada','alertada') and m.classe in ('emergencial','importante') order by {_ORDEM} limit ?", (limite,))]


def listar(con, agora, prioridade_min: int = 1, dias: int = 7, limite: int = 50) -> list[dict]:
    """E-mails triados que não são lixo, dos últimos `dias`, com prioridade mínima; os mais urgentes primeiro."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS} from email_msg m join email_fonte f on f.id=m.fonte_id "
        f"where f.estado='sim' and m.estado in ('classificada','alertada') and m.classe in ('emergencial','importante','normal') "
        f"and coalesce(m.prioridade, 0)>=? and m.recebida_em>=? order by {_ORDEM} limit ?", (prioridade_min, corte, limite))]


def na_lixeira(con, dias: int = 30, agora=None, limite: int = 200) -> list[dict]:
    """O que a Gabi mandou para a lixeira nos últimos `dias` (o Gmail a esvazia em 30), o mais recente primeiro, para o dono restaurar."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS}, m.atualizado_em as movida_em from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where f.estado='sim' and m.estado='na_lixeira' and m.atualizado_em>=? order by m.atualizado_em desc, m.id desc limit ?", (corte, limite))]
