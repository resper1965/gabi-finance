"""Produtor de avisos: grava em `aviso` o que o Ricardo precisa saber (rodada parada, conta atrasada, assinatura cancelada e cobrada,
o que vence hoje, serviço que falhou). Consome: db (rodada, compromisso, assinatura, lancamento, aviso). Só grava; entregar é outra etapa.

Um aviso por (tipo, chave) por dia de Brasília, aberto ou lido. O payload leva só nome, valor e datas: nunca CPF, documento, conta ou chave PIX.
Uso: python -m gabi.avisos            (timer de 15 min)    |    python -m gabi.avisos --falha gabi-brain-saldos.service  (OnFailure=)"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi import atividades, projetos
from gabi.agenda import consulta as consulta_agenda
from gabi.agenda import convites
from gabi.db import conectar, migrar
from gabi.dinheiro.conciliacao import CONFIRMADO
from gabi.dinheiro.valor import formatar
from gabi.envelope import bancos_antigos

BRT = ZoneInfo("America/Sao_Paulo")
HORAS_DADOS_ANTIGOS = 72
JANELA_ENTREGA = dt.timedelta(days=2)  # idade máxima para o Telegram enviar um aviso (telegram.py usa esta mesma constante)


def _inicio_do_dia_utc(agora: dt.datetime) -> str:
    d = agora.astimezone(BRT).date()
    return dt.datetime(d.year, d.month, d.day, tzinfo=BRT).astimezone(dt.timezone.utc).isoformat()


UMA_VEZ = {"atividade_hora", "convite_agenda"}  # chave = atividade + vencimento: o aviso "agora" sai uma vez só (a janela de 2 dias do produtor não pode reenviá-lo)
SEMANAL = {"conta_atrasada", "cobrada_apos_cancelar", "exportacao_parada", "servico_falhou", "projeto_parado"}  # persistem por dias: um aviso aberto por vez, lembrete a cada 7 dias depois de lido
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
    if tipo in UMA_VEZ and con.execute("select 1 from aviso where tipo=? and json_extract(payload,'$.chave')=?", (tipo, str(chave))).fetchone():
        return None  # a chave já leva o vencimento: avisado uma vez, nunca de novo nos dias seguintes
    ja = con.execute("select 1 from aviso where tipo=? and json_extract(payload,'$.chave')=? and criado_em>=?", (tipo, str(chave), _inicio_do_dia_utc(agora))).fetchone()
    if ja:
        return None
    novo_id = con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)",
                          (tipo, json.dumps({"chave": str(chave), **payload}, ensure_ascii=False), agora.astimezone(dt.timezone.utc).isoformat())).lastrowid
    if tipo in TIPOS_REVALIDADOS:
        consolidar_duplicados(con, agora)  # o recém-criado é o mais recente: os velhos da mesma conta ficam superados
    if tipo == "atividade_resumo":  # a chave é o dia: o resumo de ontem não enviado fica superado pelo de hoje
        ts = agora.astimezone(dt.timezone.utc).isoformat()
        for r in con.execute("select id, telegram_em from aviso where tipo='atividade_resumo' and entregue_em is null and id<?", (novo_id,)).fetchall():
            _fechar(con, r["id"], r["telegram_em"] is not None, ts)
    return novo_id


VALE, RESOLVIDO, INCERTO = "vale", "resolvido", "incerto"


def _item_estado(con, i: dict):
    if i.get("id") is not None:
        r = con.execute("select estado from compromisso where id=?", (str(i["id"]),)).fetchone()
    else:  # payload anterior à gravação do id: casa por nome+vencimento
        r = con.execute("select estado from compromisso where nome=? and vencimento=? order by estado='aberto' desc", (i.get("nome"), i.get("vencimento"))).fetchone()
    return r[0] if r else None


def revalidar(con, tipo: str, payload: dict) -> tuple[str, dict]:
    """Releitura (só leitura) da condição do aviso NO MOMENTO da entrega: o gabi.brain nunca anuncia o que deixou de ser verdade.
    -> (estado, payload_atual). Estados: "vale" (pode enviar), "resolvido" (condição acabou: fechar SEM enviar), "incerto" (não enviar e NÃO fechar: reavalia na próxima rodada).
    conta_atrasada: compromisso `atrasado` = vale; `a_conferir` ou linha inexistente = incerto; qualquer outro estado (pago, aberto por vencimento movido) = resolvido.
    vence_hoje: o payload atual traz só os itens ainda 'aberto' (por id; sem id, nome+vencimento); nenhum = resolvido. Entregue em outro dia, o item que virou
    `atrasado` sai (resolvido): quem assume é o conta_atrasada. cobrada_apos_cancelar: vale se a assinatura segue em `cancelar`.
    documento_vence: resolvido se o documento ou o titular saiu, se a data dele mudou ou se há outro documento ativo do mesmo titular e tipo
    com data posterior (renovação aprovada). Demais tipos: sempre valem."""
    if tipo == "conta_atrasada":
        r = con.execute("select estado from compromisso where id=?", (str(payload.get("chave")),)).fetchone()
        if r is None or r[0] == "a_conferir":
            return INCERTO, payload
        return (VALE if r[0] == "atrasado" else RESOLVIDO), payload
    if tipo == "vence_hoje":
        estados = [(i, _item_estado(con, i)) for i in payload.get("itens") or []]
        itens = [i for i, e in estados if e == "aberto"]
        if itens:
            return VALE, {**payload, "itens": itens}
        return (INCERTO if any(e == "a_conferir" for _, e in estados) else RESOLVIDO), payload
    if tipo == "vence_em_breve":
        itens, a_conferir = [], False
        for i in payload.get("itens") or []:
            r = con.execute("select estado, forma, valor_centavos, valor_fonte from compromisso where id=?", (str(i.get("id")),)).fetchone()
            if r is None:
                continue
            a_conferir = a_conferir or r["estado"] == "a_conferir"
            if r["estado"] in ABERTOS_A_VENCER:  # valor e marca de estimado são os de AGORA: o real que chegou substitui o estimado
                itens.append({**i, "valor": _valor(r["valor_centavos"]), "valor_centavos": r["valor_centavos"], "estimado": _estimado(r["valor_centavos"], r["valor_fonte"]),
                              "debito_automatico": r["forma"] == "debito_automatico"})
        if itens:
            return VALE, {**payload, "itens": itens}
        return (INCERTO if a_conferir else RESOLVIDO), payload
    if tipo == "cobrada_apos_cancelar":
        ok = con.execute("select 1 from assinatura where id=? and status='cancelar'", (str(payload.get("chave")),)).fetchone() is not None
        return (VALE if ok else RESOLVIDO), payload
    if tipo == "teams_sem_resposta":
        conta, _, chat_id = str(payload.get("chave") or "").partition("|")
        r = con.execute("select c.ultima_para_mim_em, c.minha_ultima_resposta_em, f.estado from teams_conversa c join teams_fonte f on f.conta=c.conta "
                        "where c.conta=? and c.chat_id=?", (conta, chat_id)).fetchone()
        if r is None or r["estado"] != "sim":
            return RESOLVIDO, payload
        from gabi.teams.regra import _dt
        para_mim, resp = _dt(r["ultima_para_mim_em"]), _dt(r["minha_ultima_resposta_em"])
        if para_mim is None or (resp is not None and resp >= para_mim):
            return RESOLVIDO, payload
        return VALE, payload
    if tipo == "documento_vence":
        return _documento_vence_estado(con, payload), payload
    if tipo in TIPOS_ATIVIDADE:
        vale, atual = atividades.revalidar_aviso(con, tipo, payload)
        return (VALE if vale else RESOLVIDO), atual
    if tipo == "projeto_parado":
        return (VALE if projetos.revalidar_aviso(con, payload) else RESOLVIDO), payload
    if tipo == "convite_agenda":  # respondido no Outlook, apagado ou remarcado: o aviso aberto some
        r = con.execute("select resposta, inicio_utc from agenda_evento where id=?", (payload.get("evento_id"),)).fetchone()
        return (VALE if r and r["resposta"] == "needsAction" and r["inicio_utc"] == payload.get("inicio_utc") else RESOLVIDO), payload
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


TIPOS_ATIVIDADE = ("atividade_hora", "atividade_hoje", "atividade_resumo")
TIPOS_REVALIDADOS = ("conta_atrasada", "vence_hoje", "cobrada_apos_cancelar", "vence_em_breve", "teams_sem_resposta", "documento_vence", "projeto_parado", "convite_agenda", *TIPOS_ATIVIDADE)
ABERTOS_A_VENCER = ("aberto",)
ANTECEDENCIA_PADRAO = 3
TOLERANCIA_VALOR = 0.10   # aviso de "valor diferente" só acima de 10% do estimado


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
    for r in con.execute(f"select id, tipo, payload, telegram_em from aviso where entregue_em is null and tipo in ({','.join('?' * len(TIPOS_REVALIDADOS))}) order by id desc", TIPOS_REVALIDADOS).fetchall():
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
    for r in con.execute(f"select id, tipo, payload, criado_em, telegram_em from aviso where entregue_em is null and tipo in ({','.join('?' * len(TIPOS_REVALIDADOS))})", TIPOS_REVALIDADOS).fetchall():
        estado = ainda_vale(con, r["tipo"], json.loads(r["payload"]))
        enviado = r["telegram_em"] is not None
        if estado == RESOLVIDO or (estado == INCERTO and not enviado and r["criado_em"] < limite):
            _fechar(con, r["id"], enviado, ts)


def _estimado(valor_centavos, valor_fonte) -> bool:
    """O valor ainda é estimativa (último pagamento ou padrão do mês) ou não existe: vira real quando a cobrança chega (`CONFIRMADO`)."""
    return valor_centavos is None or valor_fonte not in CONFIRMADO


def _valor(c) -> str | None:
    return None if c is None else formatar(c)


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


UNIDADE_HERMES = "hermes-gateway"


def estado_do_servico(unidade: str) -> str | None:
    """'active', 'failed', 'inactive'... ou None se não deu para saber (sem systemctl, sem permissão, unidade inexistente)."""
    import subprocess
    try:
        r = subprocess.run(["systemctl", "show", unidade, "-p", "LoadState", "-p", "ActiveState"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    campos = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
    if r.returncode != 0 or campos.get("LoadState") != "loaded":
        return None
    return campos.get("ActiveState")


def _hermes_parado(con, agora: dt.datetime, novo, estado) -> None:
    """H4: o canal (Hermes) caiu? Só 'failed' ou 'inactive' avisam; 'activating', 'reloading' e 'não sei' não. Um aviso por dia, sem texto de conversa.
    O aviso sai pelo Telegram do próprio brain, que não depende do Hermes."""
    if _parametro(con, "avisos.vigiar_hermes", True) is False:
        return
    unidade = _parametro(con, "avisos.hermes_unidade", UNIDADE_HERMES)
    unidade = unidade if isinstance(unidade, str) and unidade.strip() else UNIDADE_HERMES
    st = estado(unidade)
    if st in ("failed", "inactive"):
        novo("hermes_parado", unidade, {"unidade": unidade, "estado": st})


def _google_parado(con, agora: dt.datetime, novo) -> None:
    """Todas as fontes Google liberadas (correio e agenda) falhando E sem sincronizar há mais de `avisos.google_horas` (padrão 2): token revogado ou expirado
    (app OAuth em modo Testing vence em 7 dias). Uma fonte funcionando basta para não avisar; recarga vazia não é falha. Um aviso por dia, só contas e contagem."""
    if _parametro(con, "avisos.vigiar_google", True) is False:
        return
    horas = _parametro(con, "avisos.google_horas", 2)
    if isinstance(horas, bool) or not isinstance(horas, (int, float)) or horas <= 0:
        horas = 2
    corte = (agora - dt.timedelta(hours=horas)).astimezone(dt.timezone.utc)
    fontes = [r for t in ("email_fonte", "agenda_fonte") for r in con.execute(
        f"select conta, sincronizada_em, ultimo_erro from {t} where provedor='google' and estado='sim'")]
    if not fontes:
        return
    for f in fontes:
        if not f["ultimo_erro"] or f["ultimo_erro"].startswith("recarga vazia"):
            return
        if f["sincronizada_em"]:
            quando = dt.datetime.fromisoformat(f["sincronizada_em"])
            if quando.tzinfo is None:
                quando = quando.replace(tzinfo=dt.timezone.utc)
            if quando >= corte:
                return
    novo("google_parado", "google", {"fontes": len(fontes), "contas": sorted({f["conta"] for f in fontes})})


def _teams_sem_resposta(con, agora: dt.datetime, novo) -> None:
    """Conversa do Teams (conta com teams_fonte 'sim') em que me chamaram (1:1) ou me mencionaram (grupo) e não respondi há N horas úteis. Sem texto de mensagem.
    Ao criar o aviso grava `ultimo_aviso_em`: a mesma mensagem não avisa de novo; mensagem nova (ultima_para_mim_em maior) avisa outra vez."""
    from gabi.teams import regra
    horas, expediente = regra.ler_config(con)
    local = agora.astimezone(regra.BRT)
    if local.weekday() >= 5 or not expediente[0] <= local.time() < expediente[1]:
        return  # fora do expediente (noite, fim de semana): nada nasce nem é enviado de madrugada
    for c in con.execute("select c.* from teams_conversa c join teams_fonte f on f.conta=c.conta where f.estado='sim' order by c.conta, c.chat_id").fetchall():
        if not regra.pendente(c, agora, horas, expediente):
            continue
        chave = f"{c['conta']}|{c['chat_id']}"
        if novo("teams_sem_resposta", chave, {"conta": c["conta"], "chat_id": c["chat_id"], "tipo_chat": c["tipo"], "de_nome": c["de_nome"], "desde": c["ultima_para_mim_em"]}) is not None:
            con.execute("update teams_conversa set ultimo_aviso_em=? where conta=? and chat_id=?", (agora.astimezone(dt.timezone.utc).isoformat(), c["conta"], c["chat_id"]))


def _vence_em_breve(con, agora: dt.datetime, hoje: dt.date, novo) -> None:
    """Contas que vencem de amanhã até `avisos.antecedencia_dias` (padrão 3) à frente e ainda não foram avisadas, com o valor estimado marcado como tal.
    Cada conta entra num aviso uma única vez (as que entram na janela depois, como boleto emitido tarde, saem no aviso do dia); o do dia do vencimento é o `vence_hoje`."""
    dias = _parametro(con, "avisos.antecedencia_dias", ANTECEDENCIA_PADRAO)
    dias = dias if isinstance(dias, int) and not isinstance(dias, bool) and 1 <= dias <= 14 else ANTECEDENCIA_PADRAO
    ja: set[str] = set()
    for r in con.execute("select payload from aviso where tipo='vence_em_breve' and criado_em>=?", ((agora - dt.timedelta(days=60)).astimezone(dt.timezone.utc).isoformat(),)):
        ja |= {str(i.get("id")) for i in json.loads(r["payload"]).get("itens") or []}
    itens = [{"id": c["id"], "nome": c["nome"], "vencimento": c["vencimento"], "valor": _valor(c["valor_centavos"]), "valor_centavos": c["valor_centavos"],
              "estimado": _estimado(c["valor_centavos"], c["valor_fonte"]), "debito_automatico": c["forma"] == "debito_automatico"}
             for c in con.execute(
                 f"select id, nome, vencimento, valor_centavos, valor_fonte, forma from compromisso where vencimento>? and vencimento<=? and estado in ({','.join('?' * len(ABERTOS_A_VENCER))}) "
                 "order by vencimento, nome", (hoje.isoformat(), (hoje + dt.timedelta(days=dias)).isoformat(), *ABERTOS_A_VENCER)) if c["id"] not in ja]
    if itens:
        novo("vence_em_breve", hoje.isoformat(), {"itens": itens})


def _valor_diferente(con, agora: dt.datetime, novo) -> None:
    """Conta avisada com valor ESTIMADO cujo valor real chegou (cobrança confirmada) ou foi paga e difere em mais de 10%: um aviso por conta, uma vez só."""
    ja = {r[0] for r in con.execute("select json_extract(payload,'$.chave') from aviso where tipo='valor_diferente'")}
    for r in con.execute("select payload from aviso where tipo='vence_em_breve' and criado_em>=?", ((agora - dt.timedelta(days=30)).astimezone(dt.timezone.utc).isoformat(),)).fetchall():
        for i in json.loads(r["payload"]).get("itens") or []:
            est = i.get("valor_centavos")
            if not i.get("estimado") or not est or str(i["id"]) in ja:
                continue
            c = con.execute("select nome, vencimento, estado, valor_centavos, valor_fonte from compromisso where id=?", (str(i["id"]),)).fetchone()
            if c is None or c["valor_centavos"] is None:
                continue
            if c["estado"] == "pago":  # o valor pago de verdade (lançamento conciliado), se houver; senão o do compromisso
                p = con.execute("select abs(l.valor_centavos) from conciliacao k join lancamento l on l.externo_id=k.tx_id where k.compromisso_id=? limit 1", (str(i["id"]),)).fetchone()
                real = p[0] if p else c["valor_centavos"]
            elif c["estado"] == "aberto" and not _estimado(c["valor_centavos"], c["valor_fonte"]):
                real = c["valor_centavos"]
            else:
                continue
            if abs(real - est) / est > TOLERANCIA_VALOR:
                ja.add(str(i["id"]))
                novo("valor_diferente", i["id"], {"nome": c["nome"], "vencimento": c["vencimento"], "estimado": formatar(est), "real": formatar(real)})


AVISAR_DIAS_PADRAO = [60, 30, 7]
DIAS_VENCIDO_SEM_AVISO = 30


def _ultima_vence(con, documento_id: int) -> str | None:
    from gabi.documentos.repositorio import DATAS_VENCE
    return con.execute(f"select max(data) from documento_data where documento_id=? and tipo in ({','.join('?' * len(DATAS_VENCE))})",
                       (documento_id, *DATAS_VENCE)).fetchone()[0]


def _documento_vence_estado(con, payload: dict) -> str:
    from gabi.documentos.repositorio import DATAS_VENCE
    try:
        documento_id = int(str(payload.get("chave")).split("|")[0])
    except ValueError:
        return RESOLVIDO
    d = con.execute("select titular_tipo, titular_id, tipo from documento where id=? and excluido_em is null", (documento_id,)).fetchone()
    if d is None or not con.execute(f"select 1 from {'pessoa' if d['titular_tipo'] == 'pessoa' else 'bem'} where id=? and excluido_em is null",
                                    (d["titular_id"],)).fetchone():
        return RESOLVIDO
    if _ultima_vence(con, documento_id) != payload.get("data"):
        return RESOLVIDO
    mais_novo = con.execute(f"select 1 from documento x join documento_data y on y.documento_id=x.id where x.titular_tipo=? and x.titular_id=? and x.tipo=?"
                            f" and x.id<>? and x.excluido_em is null and y.tipo in ({','.join('?' * len(DATAS_VENCE))}) and y.data>? limit 1",
                            (d["titular_tipo"], d["titular_id"], d["tipo"], documento_id, *DATAS_VENCE, payload.get("data"))).fetchone()
    return RESOLVIDO if mais_novo else VALE


def _documento_vence(con, hoje: dt.date, novo) -> None:
    """Documento aprovado com validade, fim de vigência ou vencimento (a última delas): um aviso por (documento, marco) de `documentos.avisar_dias`
    (padrão 60, 30 e 7 dias), só o menor marco já alcançado (quem entra a 20 dias recebe o de 30, não o de 60). Vencido há mais de 30 dias não avisa
    (o passaporte antigo aprovado agora não vira alerta). Data trocada no próprio documento (renovação no lugar) volta a avisar. Payload sem número."""
    from gabi.documentos.repositorio import vencimentos
    marcos = _parametro(con, "documentos.avisar_dias", AVISAR_DIAS_PADRAO)
    if not (isinstance(marcos, list) and marcos and all(isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 365 for m in marcos)):
        marcos = AVISAR_DIAS_PADRAO
    for v in vencimentos(con, hoje, max(marcos) // 28 + 1):
        dias = (dt.date.fromisoformat(v["data"]) - hoje).days
        alcancados = [m for m in marcos if dias <= m]
        if not alcancados or dias < -DIAS_VENCIDO_SEM_AVISO:
            continue
        chave = f"{v['documento_id']}|{min(alcancados)}"
        if con.execute("select 1 from aviso where tipo='documento_vence' and json_extract(payload,'$.chave')=? and json_extract(payload,'$.data')=?",
                       (chave, v["data"])).fetchone():
            continue
        novo("documento_vence", chave, {"titular_nome": v["titular_nome"], "tipo": v["tipo"], "data_tipo": v["data_tipo"], "data": v["data"], "dias": dias})


def _bancos_desatualizados(con, agora: dt.datetime, novo) -> None:
    """Um aviso por banco por dia quando o provedor não atualiza o banco há mais de 24 h (regra única em `envelope.bancos_antigos`)."""
    for b in bancos_antigos(con, agora):
        novo("banco_desatualizado", b["banco"], b)


def _saldo_divergente(con, novo) -> None:
    """Conferência de saldo que não bateu na ÚLTIMA rodada de extratos, por conta liberada: só informa (ADR-023); um por conta por dia (chave = conta)."""
    r = con.execute("select id from rodada where fonte='open-finance' and fim is not null and status='ok' order by id desc limit 1").fetchone()
    if r is None:
        return
    for c in con.execute("select cf.conta_id, cf.detalhe, coalesce(ct.apelido, ct.instituicao) as nome from conferencia cf join conta ct on ct.id=cf.conta_id "
                         "where cf.rodada_id=? and cf.ok=0 and ct.estado='sim' and ct.excluido_em is null order by cf.conta_id", (r["id"],)):
        m = re.search(r"diferença de (-?\d+) centavos", c["detalhe"] or "")
        novo("saldo_divergente", c["conta_id"], {"conta_id": c["conta_id"], "conta": c["nome"], "diferenca_centavos": int(m.group(1)) if m else None,
                                                 "detalhe": c["detalhe"]})


def gerar_avisos(con, agora: dt.datetime, estado_servico=None) -> list[int]:
    criados: list[int] = []
    hoje = agora.astimezone(BRT).date()
    _fechar_obsoletos(con, agora)

    def novo(*a):
        i = _novo(con, agora, *a)
        if i is not None:
            criados.append(i)
        return i

    ult = con.execute("select conferida, fim from rodada where fonte='open-finance' and fim is not null order by id desc limit 2").fetchall()
    if len(ult) == 2 and not any(r["conferida"] for r in ult):
        novo("rodada_parada", "duas_nao_conferidas", {"motivo": "as 2 últimas rodadas de extratos falharam"})
    elif ult:
        conf = con.execute("select max(fim) from rodada where fonte='open-finance' and conferida=1").fetchone()[0]
        if conf is None or agora - dt.datetime.fromisoformat(conf) > dt.timedelta(hours=HORAS_DADOS_ANTIGOS):
            novo("rodada_parada", "dados_antigos", {"motivo": f"nenhuma rodada de extratos terminou bem nas últimas {HORAS_DADOS_ANTIGOS} horas"})

    _saldo_divergente(con, novo)

    ref = con.execute("select coalesce((select max(fim) from rodada where fonte='exportacao' and status='ok'), min(inicio)) from rodada").fetchone()[0]
    if ref and agora - dt.datetime.fromisoformat(ref) > dt.timedelta(hours=HORAS_EXPORTACAO):
        novo("exportacao_parada", "semanal", {"motivo": "sem pacote exportado há mais de 9 dias (falta /etc/gabi/backup.pub ou a exportação falhou)"})

    _bancos_desatualizados(con, agora, novo)
    if estado_servico is not None:  # só o timer passa o leitor real (systemctl); nos testes ninguém consulta o systemd
        _hermes_parado(con, agora, novo, estado_servico)
    _google_parado(con, agora, novo)
    _teams_sem_resposta(con, agora, novo)

    for c in con.execute("select id, nome, vencimento, valor_centavos from compromisso where estado='atrasado' and vencimento<? order by vencimento", (hoje.isoformat(),)):
        novo("conta_atrasada", c["id"], {"nome": c["nome"], "vencimento": c["vencimento"], "valor": _valor(c["valor_centavos"])})

    for a in con.execute("select id, estabelecimento, status_em from assinatura where status='cancelar' and status_em is not null"):
        d = con.execute("select data, -valor_centavos v from lancamento where natureza like '%custo%' and valor_centavos<0 and data>? "
                        "and (estabelecimento=? or descricao_original like ?) order by data desc limit 1", (a["status_em"][:10], a["estabelecimento"], f"{a['estabelecimento']}%")).fetchone()
        if d:
            novo("cobrada_apos_cancelar", a["id"], {"nome": a["estabelecimento"], "ultimo_debito": d["data"], "valor": formatar(d["v"])})

    itens = [{"id": c["id"], "nome": c["nome"], "valor": _valor(c["valor_centavos"]), "vencimento": c["vencimento"]} for c in con.execute(
        "select id, nome, vencimento, valor_centavos from compromisso where vencimento=? and estado='aberto' and coalesce(forma,'')<>'debito_automatico' order by nome", (hoje.isoformat(),))]
    if itens:
        novo("vence_hoje", hoje.isoformat(), {"itens": itens})
    _vence_em_breve(con, agora, hoje, novo)
    _valor_diferente(con, agora, novo)
    _documento_vence(con, hoje, novo)
    n = con.execute("select count(*) from lancamento where convertido=0").fetchone()[0]
    if n:  # só a contagem: nunca valor nem descrição
        novo("lancamento_sem_conversao", hoje.isoformat(), {"quantidade": n})
    for tipo, chave, p in atividades.avisos_devidos(con, agora):
        novo(tipo, chave, p)
    for p in projetos.parados(con, agora):
        novo("projeto_parado", p["id"], p)
    fuso = consulta_agenda.fuso_da_agenda(con)
    for i in convites.pendentes(con, agora):
        novo("convite_agenda", f"{i['evento_id']}:{i['inicio_utc']}",
             {"evento_id": i["evento_id"], "titulo": i["titulo"], "inicio_utc": i["inicio_utc"], "texto": convites.texto_aviso(i, fuso)})
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
        print("avisos criados:", gerar_avisos(con, agora, estado_servico=estado_do_servico))
    return 0


if __name__ == "__main__":
    sys.exit(main())
