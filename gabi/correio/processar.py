"""Processamento do correio (spec 2026-10-11-email-design, §3.5 a §3.7): classifica as mensagens novas, decide a lixeira POR REGRAS (nunca só pelo
modelo), alerta emergências (um aviso por conversa), resume o dia e apaga trechos antigos. Nada é movido sem: classe `lixo` válida, sinal de lista,
remetente não protegido, confiança no limiar, conta com a lixeira ligada E a conferência dos "já respondi" feita. A chamada à ponte fica fora de
transação. Nenhum texto de e-mail em exceção, log ou saída (só contagens)."""
import datetime as dt
import json
import time
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from gabi.avisos import _inicio_do_dia_utc, _novo
from gabi.correio.classificar import Classe, classificar, decidir_lixeira
from gabi.correio.regras import endereco, protegido, texto_protegido
from gabi.correio.sincronizar import JANELA_PADRAO, respondidos_prontos
from gabi.escuta.classificar import Falha

BRT = ZoneInfo("America/Sao_Paulo")
BACKOFF_BASE_MIN = 5
BACKOFF_MAX_H = 6
MAX_TENTATIVAS = 8
LOTE_LIXEIRA = 100
ITENS_RESUMO = 10
HORA_RESUMO = 18
LIMIAR_PADRAO = 0.9
ALERTA_RECENTE_H = 48   # só o que chegou nas últimas 48 h vira alerta no celular; o resto fica na fila de prioridades, sem notificar
ALERTAS_DIA_PADRAO = 5
ENDERECOS_POR_CONSULTA = 20


@dataclass(frozen=True)
class Limites:
    max_por_rodada: int = 60
    tempo_max_s: float = 210.0


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else padrao
    except (ValueError, TypeError):
        return padrao


def _positivo(v, padrao):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else padrao


def alertas_por_dia(con) -> int:
    v = _parametro(con, "email.max_alertas_dia", ALERTAS_DIA_PADRAO)
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 50 else ALERTAS_DIA_PADRAO


def limites_do_banco(con) -> Limites:
    return Limites(int(_positivo(_parametro(con, "email.max_por_rodada", 60), 60)), float(_positivo(_parametro(con, "email.tempo_max_s", 210), 210)))


def _utc(agora: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(agora)
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)


def _adiar(con, linha, agora: str, c: dict) -> None:
    """Falha temporária: espera crescente (5 min × 2^n, no máximo 6 h); na 8ª vira `falhou`. Nunca guarda texto de erro."""
    tent = linha["tentativas"] + 1
    if tent >= MAX_TENTATIVAS:
        con.execute("update email_msg set estado='falhou', tentativas=?, proxima_em=null, atualizado_em=? where id=?", (tent, agora, linha["id"]))
        c["falhou"] += 1
        return
    espera = min(dt.timedelta(hours=BACKOFF_MAX_H), dt.timedelta(minutes=BACKOFF_BASE_MIN * 2 ** (tent - 1)))
    con.execute("update email_msg set tentativas=?, proxima_em=?, atualizado_em=? where id=?", (tent, (_utc(agora) + espera).isoformat(), agora, linha["id"]))
    c["adiadas"] += 1


def _alertar(con, linha, classe: Classe, agora: str, maximo: int) -> str:
    """`alertou` | `repetido` (a conversa já tem alerta, para sempre) | `excesso` (passou do teto diário: um aviso agrupado por dia) | `antigo` (chegou há mais de
    48 h: sem notificar). Só `alertou` cria aviso individual."""
    now = _utc(agora)
    if _utc(linha["recebida_em"]) < now - dt.timedelta(hours=ALERTA_RECENTE_H):
        return "antigo"
    thread = linha["thread_id"] or linha["externo_id"]
    if con.execute("select 1 from aviso where tipo='email_emergencial' and json_extract(payload,'$.chave')=?", (thread,)).fetchone():
        return "repetido"
    hoje = con.execute("select count(*) from aviso where tipo='email_emergencial' and criado_em>=? and json_extract(payload,'$.chave') not like 'excesso-%'",
                       (_inicio_do_dia_utc(now),)).fetchone()[0]
    if hoje >= maximo:
        dia = now.astimezone(BRT).date().isoformat()
        _novo(con, now, "email_emergencial", f"excesso-{dia}",
              {"remetente": "vários remetentes", "assunto": f"mais e-mails emergenciais além do limite de {maximo} por dia", "motivo": "veja Mensagens › Prioridades"})
        return "excesso"
    _novo(con, now, "email_emergencial", thread, {"remetente": linha["remetente"] or "", "assunto": linha["assunto"] or "", "motivo": classe.motivo})
    return "alertou"


def fechar_alerta(con, thread_id: str, agora: str) -> int:
    """Fecha o aviso emergencial da conversa (ao restaurar ou resolver). Devolve quantos fechou."""
    return con.execute("update aviso set entregue_em=? where tipo='email_emergencial' and entregue_em is null and json_extract(payload,'$.chave')=?",
                       (_utc(agora).isoformat(), thread_id)).rowcount


def _liberar_por_resposta(con, ponte, conta: str, itens: list, agora: str, c: dict) -> list:
    """Conferência AO VIVO de "o dono já respondeu a este remetente?" (uma consulta por endereço, em lotes), sem o limite da lista dos enviados recentes.
    Respondeu: a mensagem fica na caixa. Consulta falhou: na dúvida também fica, e a mensagem espera para tentar de novo. Devolve só as que podem ir."""
    por_endereco: dict[str, list] = {}
    for x in itens:
        por_endereco.setdefault(endereco(x["remetente"]) or "", []).append(x)
    livres = []
    enderecos = [a for a in por_endereco if a]
    for i in range(0, len(enderecos), ENDERECOS_POR_CONSULTA):
        lote = enderecos[i:i + ENDERECOS_POR_CONSULTA]
        try:
            res = ponte.respondeu_a(conta, lote)
        except Exception:  # noqa: BLE001 - ponte fora do ar ou Gmail com erro: nada é movido neste lote
            res = None
        for a in lote:
            for x in por_endereco[a]:
                if res is None or not isinstance(res, dict) or a not in res:
                    _adiar(con, x, agora, c)
                elif res[a] is True:
                    con.execute("update email_msg set estado='classificada', atualizado_em=? where id=? and estado='nova'", (agora, x["id"]))
                else:
                    livres.append(x)
    return livres


def _mover(con, ponte, fonte_id: int, conta: str, itens: list, agora: str, c: dict) -> None:
    atual = con.execute("select estado, lixeira from email_fonte where id=?", (fonte_id,)).fetchone()
    if atual is None or atual["estado"] != "sim" or not atual["lixeira"]:
        # o dono desligou a conta ou a lixeira enquanto a rodada trabalhava (a chave de segurança vale na hora): ninguém é movido
        con.executemany("update email_msg set estado='classificada', atualizado_em=? where id=? and estado='nova'", [(agora, x["id"]) for x in itens])
        return
    itens = _liberar_por_resposta(con, ponte, conta, itens, agora, c)
    for i in range(0, len(itens), LOTE_LIXEIRA):
        lote = itens[i:i + LOTE_LIXEIRA]
        try:
            res = ponte.lixeira(conta, [x["externo_id"] for x in lote])
        except Exception:  # noqa: BLE001 - ponte fora do ar: o lote inteiro espera
            res = {}
        for x in lote:
            if isinstance(res, dict) and res.get(x["externo_id"]) == "ok":
                con.execute("update email_msg set estado='na_lixeira', atualizado_em=? where id=? and estado='nova'", (agora, x["id"]))
                c["lixeira"] += 1
            else:
                _adiar(con, x, agora, c)


def processar(con, cliente, orcamento, ponte, agora: str, limites: Limites | None = None, *, relogio=time.monotonic) -> dict:
    """Só mensagens `nova` de fontes liberadas, dentro da janela, as mais recentes primeiro, até `max_por_rodada` e `tempo_max_s`.
    Devolve só contagens: classificadas, emergenciais, lixeira, adiadas, falhou, invalidas, sem_modelo, tempo."""
    limites = limites or limites_do_banco(con)
    janela = _parametro(con, "email.janela_dias", JANELA_PADRAO)
    janela = janela if isinstance(janela, int) and not isinstance(janela, bool) and janela >= 1 else JANELA_PADRAO
    corte = (_utc(agora) - dt.timedelta(days=janela)).isoformat()
    criterios = _parametro(con, "email.criterios_emergencia", "")
    limiar = _parametro(con, "email.lixeira_confianca", LIMIAR_PADRAO)
    limiar = float(limiar) if isinstance(limiar, (int, float)) and not isinstance(limiar, bool) and 0.7 <= limiar <= 1 else LIMIAR_PADRAO  # piso 0,7: valor menor (banco editado à mão) cai no padrão
    c = {"classificadas": 0, "emergenciais": 0, "lixeira": 0, "adiadas": 0, "falhou": 0, "invalidas": 0, "sem_modelo": 0, "tempo": False}
    pendentes = con.execute(
        "select m.*, f.conta, f.lixeira as conta_lixeira from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where f.estado='sim' and m.estado='nova' and m.recebida_em>=? and (m.proxima_em is null or m.proxima_em<=?) "
        "order by m.recebida_em desc, m.id desc limit ?", (corte, _utc(agora).isoformat(), limites.max_por_rodada)).fetchall()
    maximo_alertas = alertas_por_dia(con)
    prontas: dict[int, bool] = {}
    a_mover: dict[int, tuple[str, list]] = {}
    motivo_sem_modelo = None
    inicio = relogio()
    for m in pendentes:
        if relogio() - inicio > limites.tempo_max_s:
            c["tempo"] = True
            break
        if m["classe"] is not None:  # retomada de uma lixeira que falhou: a classificação já paga é reaproveitada
            classe = Classe(m["classe"], m["prioridade"] or 0, m["motivo"] or "", m["confianca"] or 0.0)
        else:
            if motivo_sem_modelo:
                c["sem_modelo"] += 1
                continue
            r = classificar({"remetente": m["remetente"], "assunto": m["assunto"], "trecho": m["trecho"], "lista": bool(m["lista"])}, criterios, cliente, orcamento)
            if isinstance(r, Falha):
                if r.temporaria:
                    _adiar(con, m, agora, c)
                else:
                    motivo_sem_modelo = r.motivo
                    c["sem_modelo"] += 1
                continue
            classe = r
            c["invalidas"] += int(r.invalida)
            c["classificadas"] += 1
            con.execute("update email_msg set classe=?, prioridade=?, motivo=?, confianca=?, atualizado_em=? where id=?",
                        (classe.classe, classe.prioridade, classe.motivo, classe.confianca, agora, m["id"]))
        if classe.classe == "emergencial":
            r = _alertar(con, m, classe, agora, maximo_alertas)
            c["emergenciais"] += int(r == "alertou")
            con.execute("update email_msg set estado=?, atualizado_em=? where id=?", ("alertada" if r in ("alertou", "repetido") else "classificada", agora, m["id"]))
            continue
        if m["fonte_id"] not in prontas:
            prontas[m["fonte_id"]] = respondidos_prontos(con, m["fonte_id"])
        protecao = protegido(con, m["fonte_id"], m["remetente"]) or texto_protegido(con, m["remetente"], m["assunto"], m["trecho"])
        if prontas[m["fonte_id"]] and decidir_lixeira(classe, bool(m["lista"]), protecao, limiar, bool(m["conta_lixeira"])):
            a_mover.setdefault(m["fonte_id"], (m["conta"], []))[1].append(m)
        else:
            con.execute("update email_msg set estado='classificada', atualizado_em=? where id=?", (agora, m["id"]))
    for fonte_id, (conta, itens) in a_mover.items():
        _mover(con, ponte, fonte_id, conta, itens, agora, c)
    if c["falhou"]:  # só a contagem: a mensagem que esgotou as tentativas não fica invisível
        _novo(con, _utc(agora), "email_falhou", "falhou", {"total": c["falhou"]})
    if motivo_sem_modelo:
        _novo(con, _utc(agora), "email_sem_modelo", "modelo", {"motivo": motivo_sem_modelo})
    return c


def resumo_do_dia(con, agora: dt.datetime) -> int | None:
    """Depois das 18h BRT, uma vez por dia: aviso com o que foi para a lixeira DESDE O ÚLTIMO RESUMO (até 10 itens e o total); o que for movido depois do
    resumo do dia entra no do dia seguinte, nada se perde. Sem nada novo na lixeira, não avisa nem avança o ponto de corte."""
    local = agora.astimezone(BRT)
    if local.hour < HORA_RESUMO:
        return None
    ate = _parametro(con, "email.resumo_ate", None)
    try:
        desde = _utc(ate) if isinstance(ate, str) else _utc(agora.isoformat()) - dt.timedelta(hours=24)
    except ValueError:
        desde = _utc(agora.isoformat()) - dt.timedelta(hours=24)
    corte = desde.isoformat()
    total = con.execute("select count(*) from email_msg where estado='na_lixeira' and atualizado_em>?", (corte,)).fetchone()[0]
    if not total:
        return None
    itens = [{"remetente": r["remetente"] or "", "assunto": r["assunto"] or ""} for r in con.execute(
        "select remetente, assunto from email_msg where estado='na_lixeira' and atualizado_em>? order by atualizado_em desc, id desc limit ?", (corte, ITENS_RESUMO))]
    aviso = _novo(con, agora, "email_lixeira_resumo", local.date().isoformat(), {"total": total, "itens": itens})
    if aviso is not None:
        con.execute("insert into parametro(chave, valor) values ('email.resumo_ate', ?) on conflict(chave) do update set valor=excluded.valor",
                    (json.dumps(agora.astimezone(dt.timezone.utc).isoformat()),))
    return aviso


def purgar_trechos(con, agora: str, dias: int) -> int:
    """Apaga só o `trecho` das mensagens recebidas há mais de `dias`; o estado e o cabeçalho ficam."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).isoformat()
    return con.execute("update email_msg set trecho=null where trecho is not null and recebida_em<?", (corte,)).rowcount


RETENCAO_MSG_PADRAO = 180
RETENCAO_MSG_MIN = 90      # acima da maior janela de leitura (60 d): a mensagem podada nunca volta numa recarga
RETENCAO_MSG_MAX = 3650
GMAIL_LIXEIRA_DIAS = 30    # o Gmail esvazia a lixeira em 30 dias: antes disso a mensagem movida ainda é recuperável
RESPONDIDOS_DIAS = 365     # janela dos enviados que alimenta `email_respondido`


def retencao_msg_dias(con) -> int:
    """`email.retencao_msg_dias` (90 a 3650; padrão 180); valor ausente, corrompido ou fora da faixa cai no padrão."""
    v = _parametro(con, "email.retencao_msg_dias", RETENCAO_MSG_PADRAO)
    return v if isinstance(v, int) and not isinstance(v, bool) and RETENCAO_MSG_MIN <= v <= RETENCAO_MSG_MAX else RETENCAO_MSG_PADRAO


def purgar_mensagens(con, agora: str, dias: int) -> int:
    """Apaga do banco as mensagens recebidas há mais de `dias` (cabeçalho incluso; o Gmail não é tocado) e os `email_respondido` velhos. Nunca poda `nova`
    (ainda a processar) nem `na_lixeira` movida há menos de 30 dias (ainda recuperável pelo painel). `email_respondido` só sai depois de passada a janela dos
    enviados (365 d) E `dias`, e a linha-sentinela da conferência fica. Devolve quantas mensagens saíram."""
    agora_utc = _utc(agora)
    corte = (agora_utc - dt.timedelta(days=dias)).isoformat()
    recuperavel = (agora_utc - dt.timedelta(days=GMAIL_LIXEIRA_DIAS)).isoformat()
    n = con.execute("delete from email_msg where recebida_em<? and estado<>'nova' and (estado<>'na_lixeira' or coalesce(atualizado_em,'')<?)", (corte, recuperavel)).rowcount
    corte_resp = (agora_utc - dt.timedelta(days=max(dias, RESPONDIDOS_DIAS + 35))).isoformat()
    con.execute("delete from email_respondido where endereco<>'' and em<?", (corte_resp,))
    return n
