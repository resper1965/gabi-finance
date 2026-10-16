"""Leitura do correio (`email_msg`) para as superfícies: Hoje, resumo da manhã, MCP `email_listar`, painel (spec 2026-10-11-email-design, §3.7).
Só lê. Só fontes liberadas; nunca o que está na lixeira, o que o modelo chamou de lixo nem o que o dono dispensou (`dispensada_em`). Assunto, remetente e trecho só saem pelos canais do dono."""
import datetime as dt
import json

CAMPOS = "m.id, f.conta, m.remetente, m.assunto, m.recebida_em, m.classe, m.prioridade, m.motivo"
_ORDEM = "case m.classe when 'emergencial' then 0 else 1 end, coalesce(m.prioridade, 0) desc, m.recebida_em desc, m.id desc"


def _utc(agora) -> dt.datetime:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    return agora if agora.tzinfo else agora.replace(tzinfo=dt.timezone.utc)


DIAS_EM_ABERTO_PADRAO = 7


def dias_em_aberto(con) -> int:
    """Por quantos dias um e-mail emergencial ou importante segue na fila (`email.dias_em_aberto`, 1 a 30; padrão 7): o resolvido há semanas não ofusca o novo."""
    r = con.execute("select valor from parametro where chave='email.dias_em_aberto'").fetchone()
    try:
        v = json.loads(r[0]) if r else DIAS_EM_ABERTO_PADRAO
    except (ValueError, TypeError):
        return DIAS_EM_ABERTO_PADRAO
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 30 else DIAS_EM_ABERTO_PADRAO


def importantes(con, limite: int = 10, agora=None, dias: int | None = None) -> list[dict]:
    """Emergenciais e importantes em aberto (classificadas ou alertadas) dos últimos `dias_em_aberto`: o emergencial primeiro, depois prioridade e data."""
    corte = (_utc(agora) - dt.timedelta(days=dias or dias_em_aberto(con))).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS} from email_msg m join email_fonte f on f.id=m.fonte_id "
        f"where f.estado='sim' and m.estado in ('classificada','alertada') and m.classe in ('emergencial','importante') and m.recebida_em>=? "
        f"and m.dispensada_em is null "
        f"order by {_ORDEM} limit ?", (corte, limite))]


def listar(con, agora, prioridade_min: int = 1, dias: int = 7, limite: int = 50) -> list[dict]:
    """E-mails triados que não são lixo, dos últimos `dias`, com prioridade mínima; os mais urgentes primeiro."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS} from email_msg m join email_fonte f on f.id=m.fonte_id "
        f"where f.estado='sim' and m.estado in ('classificada','alertada') and m.classe in ('emergencial','importante','normal') "
        f"and m.dispensada_em is null and coalesce(m.prioridade, 0)>=? and m.recebida_em>=? order by {_ORDEM} limit ?", (prioridade_min, corte, limite))]


def na_lixeira(con, dias: int = 30, agora=None, limite: int = 200) -> list[dict]:
    """O que a Gabi mandou para a lixeira nos últimos `dias` (o Gmail a esvazia em 30), o mais recente primeiro, para o dono restaurar.
    Inclui contas desligadas depois (a restauração segue possível): `conta_desligada` deixa o painel avisar."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [{**r, "conta_desligada": r["conta_desligada"] != "sim"} for r in (dict(x) for x in con.execute(
        f"select {CAMPOS}, m.atualizado_em as movida_em, f.estado as conta_desligada from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where m.estado='na_lixeira' and m.atualizado_em>=? order by m.atualizado_em desc, m.id desc limit ?", (corte, limite)))]


def lixo_sugerido(con, dias: int = 30, agora=None, limite: int = 200) -> list[dict]:
    """Lixo que o modelo apontou e que NÃO foi movido (lixeira desligada na conta, confiança abaixo do limiar, remetente protegido...), dos últimos `dias`.
    Só sugestão: o dono decide mover (lixeira recuperável) ou marcar "não é lixo". `conta_lixeira` diz se a conta aceita o movimento."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS}, f.lixeira as conta_lixeira from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where f.estado='sim' and m.estado='classificada' and m.classe='lixo' and m.recebida_em>=? order by m.recebida_em desc, m.id desc limit ?", (corte, limite))]


def dispensadas(con, dias: int = 30, agora=None, limite: int = 200) -> list[dict]:
    """O que o dono dispensou nos últimos `dias` (para desfazer), a mais recente primeiro."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).astimezone(dt.timezone.utc).isoformat()
    return [dict(r) for r in con.execute(
        f"select {CAMPOS}, m.dispensada_em from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where f.estado='sim' and m.dispensada_em is not null and m.dispensada_em>=? order by m.dispensada_em desc, m.id desc limit ?", (corte, limite))]
