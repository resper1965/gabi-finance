"""Conferências de uma rodada de captura. Só uma rodada 100% conferida avança o `dados_ate` (envelope).

Regras calibradas com dado real em 09/10/2026: ver docs/adr/009-regra-de-buraco.md.
RISCO CONHECIDO: `saldo_final` é uma heurística (não há saldo inicial no Open Finance): compara a variação do saldo
entre dois fechamentos de dia com a soma dos lançamentos postados. Calibrar com dados reais (G4). Consome: dinheiro.previstas.
"""
import datetime as dt
import statistics
from dataclasses import dataclass

from gabi.dinheiro import previstas

JANELA_BURACO = 14      # dias olhados para trás
HISTORICO_BURACO = 56   # dias usados para saber em que dias da semana a conta costuma ter movimento
MINIMO_HISTORICO = 21   # menos que isso: sem base para afirmar buraco
FRACAO_ESPERADO = 0.5   # dia da semana com movimento em >= 50% das semanas é dia "esperado"
VOLUME_MINIMO = 0.5     # ontem >= 50% da mediana dos dias úteis anteriores
MEDIANA_MINIMA = 2
MIN_SEGUIDOS = 2        # buraco só reprova com >= 2 dias úteis SEGUIDOS sem movimento (calibrado com dado real, 09/10/2026; ADR-009)


@dataclass(frozen=True)
class Conferencia:
    tipo: str
    conta_id: int
    ok: bool
    detalhe: str


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def _util(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in previstas.feriados(d.year)


def _saldo_final(con, conta_id: int, tipo: str) -> tuple[bool, str]:
    if tipo == "CREDIT":
        return True, "cartão: sem conferência de saldo"
    snaps = con.execute("select em, saldo_centavos from saldo where conta_id=? order by em", (conta_id,)).fetchall()
    if not snaps:
        return True, "sem base (nenhum saldo registrado)"
    atual = snaps[-1]
    dia = atual["em"][:10]
    anteriores = [s for s in snaps if s["em"][:10] < dia]
    if not anteriores:
        return True, "sem base (menos de 2 dias de saldo)"
    base = anteriores[-1]
    esperado = con.execute(
        "select coalesce(sum(valor_centavos),0) from lancamento where conta_id=? and status='posted' and data>? and data<=?",
        (conta_id, base["em"][:10], dia)).fetchone()[0]
    variacao = atual["saldo_centavos"] - base["saldo_centavos"]
    dif = variacao - esperado
    if dif == 0:
        return True, f"variação do saldo {variacao} = lançamentos {esperado} (centavos)"
    from gabi.dinheiro.contas_pagar import faturas_abertas  # import tardio: contas_pagar não depende de conferência
    for f in faturas_abertas(con, _d(dia)):  # saída do saldo = débito de fatura que o banco ainda não publicou como lançamento
        if dif == -f["total_centavos"]:
            return True, f"diferença de {dif} centavos explicada pela fatura {f['id']} (débito ainda não publicado no extrato)"
    return False, f"variação do saldo {variacao} ≠ lançamentos {esperado}: diferença de {dif} centavos"


def _dias_sem_buraco(con, conta_id: int, hoje: dt.date, tipo: str = "BANK") -> tuple[bool, str]:
    if tipo == "CREDIT":
        return True, "cartão: sem conferência de buraco (gasto irregular)"
    dias = {_d(r[0]) for r in con.execute("select distinct data from lancamento where conta_id=? and data<=?", (conta_id, hoje.isoformat()))}
    if not dias or (hoje - min(dias)).days < MINIMO_HISTORICO:
        return True, f"sem base (histórico menor que {MINIMO_HISTORICO} dias)"
    hist = [hoje - dt.timedelta(days=k) for k in range(1, HISTORICO_BURACO + 1)]
    esperado = {}
    for w in range(5):  # só dias úteis; fim de semana e feriado nunca contam como buraco
        dw = [d for d in hist if d.weekday() == w and _util(d)]
        esperado[w] = bool(dw) and sum(d in dias for d in dw) / len(dw) >= FRACAO_ESPERADO
    buracos = [d for d in (hoje - dt.timedelta(days=k) for k in range(1, JANELA_BURACO + 1))
               if _util(d) and esperado[d.weekday()] and d not in dias]
    if buracos:
        lista = ", ".join(d.isoformat() for d in sorted(buracos))
        if _maior_sequencia(buracos) >= MIN_SEGUIDOS:
            return False, "dias úteis sem movimento: " + lista
        return True, "dias úteis isolados sem movimento (não reprova): " + lista
    return True, "nenhum dia útil esperado sem movimento"


def _maior_sequencia(dias: list[dt.date]) -> int:
    """Maior número de dias ÚTEIS consecutivos (fim de semana e feriado não interrompem) dentro de `dias`."""
    conj, melhor = set(dias), 0
    for d in conj:
        ant = d - dt.timedelta(days=1)
        while not _util(ant):
            ant -= dt.timedelta(days=1)
        if ant in conj:
            continue  # não é o começo de uma sequência
        n, atual = 1, d
        while True:
            atual += dt.timedelta(days=1)
            while not _util(atual):
                atual += dt.timedelta(days=1)
            if atual not in conj:
                break
            n += 1
        melhor = max(melhor, n)
    return melhor


def _volume_proximo(con, conta_id: int, hoje: dt.date, tipo: str = "BANK") -> tuple[bool, str]:
    if tipo == "CREDIT":
        return True, "cartão: sem conferência de volume (gasto irregular)"
    ontem = hoje - dt.timedelta(days=1)
    if not _util(ontem):
        return True, "ontem não teve expediente"
    cont = {_d(r[0]): r[1] for r in con.execute(
        "select data, count(*) from lancamento where conta_id=? and data>=? and data<=? group by data",
        (conta_id, (ontem - dt.timedelta(days=14)).isoformat(), ontem.isoformat()))}
    base = [cont.get(d, 0) for d in (ontem - dt.timedelta(days=k) for k in range(1, 15)) if _util(d)]
    if len(base) < 5:
        return True, "sem base (poucos dias úteis anteriores)"
    med = statistics.median(base)
    n = cont.get(ontem, 0)
    if med < MEDIANA_MINIMA:
        return True, f"mediana baixa ({med}); ontem {n}"
    if n < VOLUME_MINIMO * med:
        return False, f"ontem {n} lançamentos; mediana dos dias úteis anteriores {med}"
    return True, f"ontem {n} lançamentos; mediana {med}"


def conferir(con, rodada_id: int, conta_id: int, hoje: dt.date) -> list[Conferencia]:
    tipo = con.execute("select tipo from conta where id=?", (conta_id,)).fetchone()["tipo"]
    resultados = [("saldo_final", *_saldo_final(con, conta_id, tipo)),
                  ("dias_sem_buraco", *_dias_sem_buraco(con, conta_id, hoje, tipo)),
                  ("volume_proximo", *_volume_proximo(con, conta_id, hoje, tipo))]
    con.execute("delete from conferencia where rodada_id=? and conta_id=?", (rodada_id, conta_id))
    agora = dt.datetime.now(dt.timezone.utc).isoformat()
    for t, ok, detalhe in resultados:
        con.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, detalhe, criado_em) values (?,?,?,?,?,?)",
                    (rodada_id, t, conta_id, int(ok), detalhe, agora))
    return [Conferencia(t, conta_id, ok, d) for t, ok, d in resultados]


def marcar_conferida(con, rodada_id: int) -> bool:
    """True (e `conferida=1`) só se a rodada terminou ok, sem aviso, e todas as conferências das contas liberadas (estado 'sim')
    passaram. Conta ainda não liberada é conferida e registrada, mas não trava o `dados_ate`; sem nenhuma liberada, não há o que afirmar."""
    r = con.execute("select status, erro from rodada where id=?", (rodada_id,)).fetchone()
    if r is None or r["status"] != "ok" or r["erro"]:
        return False
    oks = [x[0] for x in con.execute(
        "select cf.ok from conferencia cf join conta c on c.id=cf.conta_id where cf.rodada_id=? and c.estado='sim' and c.excluido_em is null", (rodada_id,))]
    if not oks or not all(oks):
        return False
    con.execute("update rodada set conferida=1 where id=?", (rodada_id,))
    return True
