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
from gabi.correio.regras import protegido
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


def _alertar(con, linha, classe: Classe, agora: str) -> bool:
    """Um aviso por conversa, para sempre (reler ou reclassificar não repete). True se criou."""
    thread = linha["thread_id"] or linha["externo_id"]
    if con.execute("select 1 from aviso where tipo='email_emergencial' and json_extract(payload,'$.chave')=?", (thread,)).fetchone():
        return False
    return _novo(con, _utc(agora), "email_emergencial", thread,
                 {"remetente": linha["remetente"] or "", "assunto": linha["assunto"] or "", "motivo": classe.motivo}) is not None


def fechar_alerta(con, thread_id: str, agora: str) -> int:
    """Fecha o aviso emergencial da conversa (ao restaurar ou resolver). Devolve quantos fechou."""
    return con.execute("update aviso set entregue_em=? where tipo='email_emergencial' and entregue_em is null and json_extract(payload,'$.chave')=?",
                       (_utc(agora).isoformat(), thread_id)).rowcount


def _mover(con, ponte, conta: str, itens: list, agora: str, c: dict) -> None:
    for i in range(0, len(itens), LOTE_LIXEIRA):
        lote = itens[i:i + LOTE_LIXEIRA]
        try:
            res = ponte.lixeira(conta, [x["externo_id"] for x in lote])
        except Exception:  # noqa: BLE001 - ponte fora do ar: o lote inteiro espera
            res = {}
        for x in lote:
            if isinstance(res, dict) and res.get(x["externo_id"]) == "ok":
                con.execute("update email_msg set estado='na_lixeira', atualizado_em=? where id=?", (agora, x["id"]))
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
    limiar = float(limiar) if isinstance(limiar, (int, float)) and not isinstance(limiar, bool) and 0 <= limiar <= 1 else LIMIAR_PADRAO
    c = {"classificadas": 0, "emergenciais": 0, "lixeira": 0, "adiadas": 0, "falhou": 0, "invalidas": 0, "sem_modelo": 0, "tempo": False}
    pendentes = con.execute(
        "select m.*, f.conta, f.lixeira as conta_lixeira from email_msg m join email_fonte f on f.id=m.fonte_id "
        "where f.estado='sim' and m.estado='nova' and m.recebida_em>=? and (m.proxima_em is null or m.proxima_em<=?) "
        "order by m.recebida_em desc, m.id desc limit ?", (corte, _utc(agora).isoformat(), limites.max_por_rodada)).fetchall()
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
            c["emergenciais"] += int(_alertar(con, m, classe, agora))
            con.execute("update email_msg set estado='alertada', atualizado_em=? where id=?", (agora, m["id"]))
            continue
        if m["fonte_id"] not in prontas:
            prontas[m["fonte_id"]] = respondidos_prontos(con, m["fonte_id"])
        if prontas[m["fonte_id"]] and decidir_lixeira(classe, bool(m["lista"]), protegido(con, m["fonte_id"], m["remetente"]), limiar, bool(m["conta_lixeira"])):
            a_mover.setdefault(m["fonte_id"], (m["conta"], []))[1].append(m)
        else:
            con.execute("update email_msg set estado='classificada', atualizado_em=? where id=?", (agora, m["id"]))
    for conta, itens in a_mover.values():
        _mover(con, ponte, conta, itens, agora, c)
    if motivo_sem_modelo:
        _novo(con, _utc(agora), "email_sem_modelo", "modelo", {"motivo": motivo_sem_modelo})
    return c


def resumo_do_dia(con, agora: dt.datetime) -> int | None:
    """Depois das 18h BRT, uma vez por dia: aviso com o que foi para a lixeira hoje (até 10 itens e o total). Sem nada na lixeira, não avisa."""
    local = agora.astimezone(BRT)
    if local.hour < HORA_RESUMO:
        return None
    inicio = _inicio_do_dia_utc(agora)
    total = con.execute("select count(*) from email_msg where estado='na_lixeira' and atualizado_em>=?", (inicio,)).fetchone()[0]
    if not total:
        return None
    itens = [{"remetente": r["remetente"] or "", "assunto": r["assunto"] or ""} for r in con.execute(
        "select remetente, assunto from email_msg where estado='na_lixeira' and atualizado_em>=? order by atualizado_em desc, id desc limit ?", (inicio, ITENS_RESUMO))]
    return _novo(con, agora, "email_lixeira_resumo", local.date().isoformat(), {"total": total, "itens": itens})


def purgar_trechos(con, agora: str, dias: int) -> int:
    """Apaga só o `trecho` das mensagens recebidas há mais de `dias`; o estado e o cabeçalho ficam."""
    corte = (_utc(agora) - dt.timedelta(days=dias)).isoformat()
    return con.execute("update email_msg set trecho=null where trecho is not null and recebida_em<?", (corte,)).rowcount
