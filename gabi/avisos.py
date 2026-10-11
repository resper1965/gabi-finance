"""Produtor de avisos: grava em `aviso` o que o Ricardo precisa saber (rodada parada, conta atrasada, assinatura cancelada e cobrada,
o que vence hoje, serviço que falhou). Consome: db (rodada, compromisso, assinatura, lancamento, aviso). Só grava; entregar é outra etapa.

Um aviso por (tipo, chave) por dia de Brasília, aberto ou lido. O payload leva só nome, valor e datas: nunca CPF, documento, conta ou chave PIX.
Uso: python -m gabi.avisos            (timer de 15 min)    |    python -m gabi.avisos --falha gabi-brain-saldos.service  (OnFailure=)"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import conectar, migrar
from gabi.dinheiro.valor import formatar

BRT = ZoneInfo("America/Sao_Paulo")
HORAS_DADOS_ANTIGOS = 72
JANELA_ENTREGA = dt.timedelta(days=2)  # idade máxima para o Telegram enviar um aviso (telegram.py usa esta mesma constante)


def _inicio_do_dia_utc(agora: dt.datetime) -> str:
    d = agora.astimezone(BRT).date()
    return dt.datetime(d.year, d.month, d.day, tzinfo=BRT).astimezone(dt.timezone.utc).isoformat()


SEMANAL = {"conta_atrasada", "cobrada_apos_cancelar", "exportacao_parada"}  # persistem por dias: um aviso aberto por vez, lembrete a cada 7 dias depois de lido
DIAS_SILENCIO = 7
HORAS_EXPORTACAO = 9 * 24


def _novo(con, agora: dt.datetime, tipo: str, chave, payload: dict) -> int | None:
    if tipo in SEMANAL:
        # aberto segura o novo; mas (tipos revalidados) aberto, nunca enviado e fora da janela de entrega não segura: ninguém o enviará mais.
        # Aviso fechado sem envio (telegram_em == entregue_em: obsoleto/incerto vencido) também não segura; só o realmente entregue/lido vale o silêncio.
        velho = ""
        if tipo in TIPOS_REVALIDADOS:
            velho = " and not (entregue_em is null and telegram_em is null and criado_em<?)"
        args = [tipo, str(chave), (agora - dt.timedelta(days=DIAS_SILENCIO)).astimezone(dt.timezone.utc).isoformat()]
        if velho:
            args.append((agora - JANELA_ENTREGA).astimezone(dt.timezone.utc).isoformat())
        if con.execute("select 1 from aviso where tipo=? and json_extract(payload,'$.chave')=? and (entregue_em is null or criado_em>=?)"
                       " and not (telegram_em is not null and telegram_em is entregue_em)" + velho, args).fetchone():
            return None
    ja = con.execute("select 1 from aviso where tipo=? and json_extract(payload,'$.chave')=? and criado_em>=?", (tipo, str(chave), _inicio_do_dia_utc(agora))).fetchone()
    if ja:
        return None
    novo_id = con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)",
                          (tipo, json.dumps({"chave": str(chave), **payload}, ensure_ascii=False), agora.astimezone(dt.timezone.utc).isoformat())).lastrowid
    if tipo in TIPOS_REVALIDADOS:
        consolidar_duplicados(con, agora)  # o recém-criado é o mais recente: os velhos da mesma conta ficam superados
    return novo_id


VALE, RESOLVIDO, INCERTO = "vale", "resolvido", "incerto"


def _item_estado(con, i: dict):
    if i.get("id") is not None:
        r = con.execute("select estado from compromisso where id=?", (str(i["id"]),)).fetchone()
    else:  # payload anterior à gravação do id: casa por nome+vencimento
        r = con.execute("select estado from compromisso where nome=? and vencimento=? order by estado in ('aberto','previsto') desc", (i.get("nome"), i.get("vencimento"))).fetchone()
    return r[0] if r else None


def revalidar(con, tipo: str, payload: dict) -> tuple[str, dict]:
    """Releitura (só leitura) da condição do aviso NO MOMENTO da entrega: o gabi.brain nunca anuncia o que deixou de ser verdade.
    -> (estado, payload_atual). Estados: "vale" (pode enviar), "resolvido" (condição acabou: fechar SEM enviar), "incerto" (não enviar e NÃO fechar: reavalia na próxima rodada).
    conta_atrasada: compromisso `atrasado` = vale; `a_conferir` ou linha inexistente = incerto; qualquer outro estado (pago, debito_automatico, aberto/previsto por vencimento movido) = resolvido.
    vence_hoje: o payload atual traz só os itens ainda 'aberto'/'previsto' (por id; sem id, nome+vencimento); nenhum = resolvido. Entregue em outro dia, o item que virou
    `atrasado` sai (resolvido): quem assume é o conta_atrasada. cobrada_apos_cancelar: vale se a assinatura segue em `cancelar`. Demais tipos: sempre valem."""
    if tipo == "conta_atrasada":
        r = con.execute("select estado from compromisso where id=?", (str(payload.get("chave")),)).fetchone()
        if r is None or r[0] == "a_conferir":
            return INCERTO, payload
        return (VALE if r[0] == "atrasado" else RESOLVIDO), payload
    if tipo == "vence_hoje":
        estados = [(i, _item_estado(con, i)) for i in payload.get("itens") or []]
        itens = [i for i, e in estados if e in ("aberto", "previsto")]
        if itens:
            return VALE, {**payload, "itens": itens}
        return (INCERTO if any(e == "a_conferir" for _, e in estados) else RESOLVIDO), payload
    if tipo == "cobrada_apos_cancelar":
        ok = con.execute("select 1 from assinatura where id=? and status='cancelar'", (str(payload.get("chave")),)).fetchone() is not None
        return (VALE if ok else RESOLVIDO), payload
    return VALE, payload


def ainda_vale(con, tipo: str, payload: dict) -> str:
    return revalidar(con, tipo, payload)[0]


def triar(con, aviso_id: int, tipo: str, payload: dict, agora: dt.datetime) -> tuple[str, dict]:
    """Passo único dos canais de entrega (Telegram e Hermes): revalida e, se "resolvido", fecha o aviso (telegram_em+entregue_em = fechado, NÃO enviado)."""
    estado, atual = revalidar(con, tipo, payload)
    if estado == RESOLVIDO:
        ts = agora.astimezone(dt.timezone.utc).isoformat()
        con.execute("update aviso set telegram_em=?, entregue_em=? where id=?", (ts, ts, aviso_id))
    return estado, atual


TIPOS_REVALIDADOS = ("conta_atrasada", "vence_hoje", "cobrada_apos_cancelar")


def _fechar(con, aviso_id: int, enviado: bool, ts: str) -> None:
    """Nunca enviado: telegram_em+entregue_em = fechado sem envio. Já enviado e não lido: só entregue_em (telegram_em segue significando "enviado")."""
    if enviado:
        con.execute("update aviso set entregue_em=? where id=?", (ts, aviso_id))
    else:
        con.execute("update aviso set telegram_em=?, entregue_em=? where id=?", (ts, ts, aviso_id))


def consolidar_duplicados(con, agora: dt.datetime) -> None:
    """Avisos repetidos da mesma conta (mesmo tipo e chave) são consolidados no mais recente: os mais velhos abertos são fechados como superados."""
    ts = agora.astimezone(dt.timezone.utc).isoformat()
    vistos: dict = {}
    for r in con.execute("select id, tipo, payload, telegram_em from aviso where entregue_em is null and tipo in (?,?,?) order by id desc", TIPOS_REVALIDADOS).fetchall():
        k = (r["tipo"], json.loads(r["payload"]).get("chave"))
        if k in vistos:
            _fechar(con, r["id"], r["telegram_em"] is not None, ts)
        else:
            vistos[k] = r["id"]


def _fechar_obsoletos(con, agora: dt.datetime) -> None:
    """Aviso aberto cuja condição JÁ RESOLVEU: fecha (nunca enviado: telegram_em+entregue_em; enviado e não lido: só entregue_em). O INCERTO nunca enviado e mais velho
    que a janela de entrega também fecha (o Telegram não o enviará mais; deixa nascer um aviso novo quando a conta voltar a `atrasado`). Incerto enviado ou dentro da janela fica."""
    ts = agora.astimezone(dt.timezone.utc).isoformat()
    limite = (agora - JANELA_ENTREGA).astimezone(dt.timezone.utc).isoformat()
    for r in con.execute("select id, tipo, payload, criado_em, telegram_em from aviso where entregue_em is null and tipo in (?,?,?)", TIPOS_REVALIDADOS).fetchall():
        estado = ainda_vale(con, r["tipo"], json.loads(r["payload"]))
        enviado = r["telegram_em"] is not None
        if estado == RESOLVIDO or (estado == INCERTO and not enviado and r["criado_em"] < limite):
            _fechar(con, r["id"], enviado, ts)


def _valor(c) -> str | None:
    return None if c is None else formatar(c)


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


def _escuta_parada(con, agora: dt.datetime, novo) -> None:
    """Vigia do ouvinte: só em modo 'ativo'; sem nenhuma mensagem registrada não avisa. Um aviso por dia, sem texto, nome nem número de telefone."""
    if _parametro(con, "escuta.modo", "registro") != "ativo":
        return
    horas = _parametro(con, "escuta.horas_sem_receber", 12)
    if isinstance(horas, bool) or not isinstance(horas, (int, float)) or horas <= 0:
        horas = 12
    ultima = con.execute("select max(recebida_em) from escuta_msg").fetchone()[0]
    if not ultima:
        return
    try:
        quando = dt.datetime.fromisoformat(ultima)
    except ValueError:
        return
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=BRT)  # o spool grava em UTC; linha antiga sem offset vale como Brasília (convenção do spool)
    if agora - quando > dt.timedelta(hours=horas):
        n = int((agora - quando).total_seconds() // 3600)
        novo("escuta_parada", "ouvinte", {"motivo": f"ouvinte sem receber mensagens há {n} horas"})


def gerar_avisos(con, agora: dt.datetime) -> list[int]:
    criados: list[int] = []
    hoje = agora.astimezone(BRT).date()
    _fechar_obsoletos(con, agora)

    def novo(*a):
        i = _novo(con, agora, *a)
        if i is not None:
            criados.append(i)

    ult = con.execute("select conferida, fim from rodada where fonte='open-finance' and fim is not null order by id desc limit 2").fetchall()
    if len(ult) == 2 and not any(r["conferida"] for r in ult):
        novo("rodada_parada", "duas_nao_conferidas", {"motivo": "as 2 últimas rodadas de extratos não foram conferidas"})
    elif ult:
        conf = con.execute("select max(fim) from rodada where fonte='open-finance' and conferida=1").fetchone()[0]
        if conf is None or agora - dt.datetime.fromisoformat(conf) > dt.timedelta(hours=HORAS_DADOS_ANTIGOS):
            novo("rodada_parada", "dados_antigos", {"motivo": f"nenhuma rodada conferida nas últimas {HORAS_DADOS_ANTIGOS} horas"})

    ref = con.execute("select coalesce((select max(fim) from rodada where fonte='exportacao' and status='ok'), min(inicio)) from rodada").fetchone()[0]
    if ref and agora - dt.datetime.fromisoformat(ref) > dt.timedelta(hours=HORAS_EXPORTACAO):
        novo("exportacao_parada", "semanal", {"motivo": "sem pacote exportado há mais de 9 dias (falta /etc/gabi/backup.pub ou a exportação falhou)"})

    _escuta_parada(con, agora, novo)

    for c in con.execute("select id, nome, vencimento, valor_centavos from compromisso where estado='atrasado' and vencimento<? order by vencimento", (hoje.isoformat(),)):
        novo("conta_atrasada", c["id"], {"nome": c["nome"], "vencimento": c["vencimento"], "valor": _valor(c["valor_centavos"])})

    for a in con.execute("select id, estabelecimento, status_em from assinatura where status='cancelar' and status_em is not null"):
        d = con.execute("select data, -valor_centavos v from lancamento where natureza like '%custo%' and valor_centavos<0 and data>? "
                        "and (estabelecimento=? or descricao_original like ?) order by data desc limit 1", (a["status_em"][:10], a["estabelecimento"], f"{a['estabelecimento']}%")).fetchone()
        if d:
            novo("cobrada_apos_cancelar", a["id"], {"nome": a["estabelecimento"], "ultimo_debito": d["data"], "valor": formatar(d["v"])})

    itens = [{"id": c["id"], "nome": c["nome"], "valor": _valor(c["valor_centavos"]), "vencimento": c["vencimento"]} for c in con.execute(
        "select id, nome, vencimento, valor_centavos from compromisso where vencimento=? and estado in ('aberto','previsto') order by nome", (hoje.isoformat(),))]
    if itens:
        novo("vence_hoje", hoje.isoformat(), {"itens": itens})
    n = con.execute("select count(*) from lancamento where convertido=0").fetchone()[0]
    if n:  # só a contagem: nunca valor nem descrição
        novo("lancamento_sem_conversao", hoje.isoformat(), {"quantidade": n})
    return criados


def registrar_servico_falhou(con, unidade: str, agora: dt.datetime) -> int | None:
    return _novo(con, agora, "servico_falhou", unidade, {"unidade": unidade})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    ap.add_argument("--falha", default=None, help="nome da unidade systemd que falhou (usado por OnFailure=)")
    a = ap.parse_args(argv)
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    agora = dt.datetime.now(dt.timezone.utc)
    if a.falha:
        print("servico_falhou:", a.falha, "->", registrar_servico_falhou(con, a.falha, agora))
    else:
        print("avisos criados:", gerar_avisos(con, agora))
    return 0


if __name__ == "__main__":
    sys.exit(main())
