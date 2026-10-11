"""Envelope de toda resposta de leitura: `dados_ate` vem da última rodada CONFERIDA, não da última tentativa (R4/Review 4)."""
import datetime as dt
import sqlite3

IGNORADAS = ("backup", "importacao-staging", "open-finance-saldos", "exportacao")  # não são fontes que se "confere" (saldos têm rodada própria; exportação é semanal)
LIMITE_DESATUALIZADO = dt.timedelta(days=3)
# Fontes COM conceito de conferência: só rodada `conferida=1` avança o frescor (hoje, só os extratos; ver dinheiro/conferencia.marcar_conferida).
# As demais nunca recebem conferida=1: valem pela última rodada `status='ok'`, contra o limite da própria agenda (timers em deploy/).
COM_CONFERENCIA = ("open-finance",)
LIMITE_FONTE = {
    "notas-nibo": dt.timedelta(hours=36),               # diária 06:40
    "comprovantes-paperless": dt.timedelta(hours=36),   # diária 07:00
    "trabalho": dt.timedelta(hours=12),                 # a cada 15 min, 06-22h (a pausa noturna chega a 8 h)
}
LIMITE_PADRAO_SEM_CONFERENCIA = dt.timedelta(hours=36)
BRT = dt.timezone(dt.timedelta(hours=-3))
HORAS_RODADAS = (6, 14)  # espelha OnCalendar de deploy/gabi-brain-extratos.timer (tests/test_envelope.py confere)


def _utc(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(s)
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d.astimezone(dt.timezone.utc)


def _z(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def proxima_rodada(agora: dt.datetime) -> str:
    """Próxima rodada de extratos (UTC, ISO Z), pelos horários de Brasília do timer."""
    b = agora.astimezone(BRT)
    for dia in (0, 1):
        for h in HORAS_RODADAS:
            c = (b + dt.timedelta(days=dia)).replace(hour=h, minute=0, second=0, microsecond=0)
            if c > b:
                return _z(c.astimezone(dt.timezone.utc))
    raise AssertionError("inalcançável")


def _trabalho_em_uso(con) -> bool:
    """`trabalho` só vale como fonte quando há caixa de e-mail ou fonte de agenda liberada (estado 'sim'); tabelas podem faltar em bancos antigos."""
    for tabela in ("caixa_email", "agenda_fonte"):
        try:
            if con.execute(f"select 1 from {tabela} where estado='sim' limit 1").fetchone():
                return True
        except sqlite3.OperationalError:
            continue
    return False


def envelope(con, dados, agora: dt.datetime | None = None) -> dict:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    fontes, ultimas, falta = [], [], False
    nomes = [r[0] for r in con.execute(f"select distinct fonte from rodada where fonte not in ({','.join('?' * len(IGNORADAS))}) order by fonte", IGNORADAS)]
    if "trabalho" in nomes and not _trabalho_em_uso(con):
        nomes.remove("trabalho")
    for nome in nomes:
        tent = con.execute("select status, conferida from rodada where fonte=? order by id desc limit 1", (nome,)).fetchone()
        if nome in COM_CONFERENCIA:
            conf = con.execute("select max(fim) from rodada where fonte=? and conferida=1", (nome,)).fetchone()[0]
            ultima = _utc(conf) if conf else None
            if tent["status"] == "erro":
                estado = "erro"
            elif not tent["conferida"]:
                estado = "nao_conferida"
            elif ultima is None or agora - ultima > LIMITE_DESATUALIZADO:
                estado = "parada"
            else:
                estado = "ok"
        else:
            ok = con.execute("select max(fim) from rodada where fonte=? and status='ok'", (nome,)).fetchone()[0]
            ultima = _utc(ok) if ok else None
            limite = LIMITE_FONTE.get(nome, LIMITE_PADRAO_SEM_CONFERENCIA)
            if tent["status"] == "erro":
                estado = "erro"
            elif ultima is None:
                estado = "nao_conferida"  # nunca rodou com sucesso
            elif agora - ultima > limite:
                estado = "parada"
            else:
                estado = "ok"
        if ultima is None:
            falta = True
        else:
            ultimas.append(ultima)
        fontes.append({"nome": nome, "estado": estado, "ultima": _z(ultima) if ultima else None})
    # a fonte mais velha manda; erro/parada desatualizam (fontes sem conferência); nunca-ok (`ultima` None) desatualiza via `falta`. Extrato com rodada nova ainda não conferida segue valendo pela última conferida
    # (extrato com última tentativa em erro segue valendo pela última conferida até o limite de 3 dias: comportamento antigo, coberto por teste)
    atrasada = any(f["estado"] in ("erro", "parada") and f["nome"] not in COM_CONFERENCIA for f in fontes)
    dados_ate = None if (falta or not ultimas) else min(ultimas)
    return {"dados_ate": _z(dados_ate) if dados_ate else None,
            "desatualizado": dados_ate is None or atrasada or agora - dados_ate > LIMITE_DESATUALIZADO,
            "proxima_rodada": proxima_rodada(agora), "fontes": fontes, "dados": dados}
