"""Envelope de toda resposta de leitura: `dados_ate` vem da última rodada CONFERIDA, não da última tentativa (R4/Review 4)."""
import datetime as dt
import sqlite3

LIMITE_DESATUALIZADO = dt.timedelta(days=3)
# FONTE ÚNICA de verdade do frescor: {fonte (nome em rodada.fonte): limite | None}. Toda fonte passada a registrar_rodada() DEVE estar aqui
# (tests/test_envelope.py varre o código): quem adiciona uma fonte escolhe o limite.
#   limite  -> conta em dados_ate/desatualizado; estado "parada" se a última rodada válida for mais velha que o limite.
#   None    -> ignorada (não é dado servido: backup, exportação semanal, saldos com rodada própria, staging).
#   ausente -> listada (ultima/estado ok|erro) mas NUNCA conta em dados_ate/desatualizado.
# Só as fontes em COM_CONFERENCIA têm conceito de conferência: valem pela última rodada `conferida=1` (dinheiro/conferencia.marcar_conferida).
# As demais valem pela última rodada `status='ok'`, contra o limite da própria agenda (timers em deploy/).
FONTES = {
    "open-finance": LIMITE_DESATUALIZADO,
    "notas-nibo": dt.timedelta(hours=30),               # diária 06:40
    "comprovantes-paperless": dt.timedelta(hours=30),   # diária 07:00
    "trabalho": dt.timedelta(hours=12),                 # a cada 15 min, 06-22h (a pausa noturna chega a 8 h); só conta se estiver em uso
    "agenda": dt.timedelta(hours=12),                   # idem (gabi-brain-agenda.timer); só conta com agenda_fonte liberada
    "correio": dt.timedelta(hours=12),                  # idem (gabi-brain-correio.timer); só conta com email_fonte liberada
    "open-finance-saldos": None, "backup": None, "exportacao": None, "importacao-staging": None,
}
COM_CONFERENCIA = ("open-finance",)
# Esperadas: devem aparecer mesmo sem nenhuma rodada (cliente sem token, timer que nunca disparou); sem rodada = nao_conferida = desatualizado.
ESPERADAS = ("notas-nibo", "comprovantes-paperless")
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


def _em_uso(con, tabela: str) -> bool:
    """Há linha liberada (estado 'sim') em `tabela`; a tabela pode faltar em bancos antigos."""
    try:
        return bool(con.execute(f"select 1 from {tabela} where estado='sim' limit 1").fetchone())
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        return False


def _trabalho_em_uso(con) -> bool:
    """`trabalho` (e-mail e tarefas) só vale como fonte com caixa de e-mail liberada."""
    return _em_uso(con, "caixa_email")


def _agenda_em_uso(con) -> bool:
    """`agenda` só vale como fonte com alguma fonte de agenda liberada: liberar agenda não liga o `trabalho`."""
    return _em_uso(con, "agenda_fonte")


def _correio_em_uso(con) -> bool:
    """`correio` só vale como fonte com alguma conta de e-mail liberada (`email_fonte` em estado 'sim')."""
    return _em_uso(con, "email_fonte")


def envelope(con, dados, agora: dt.datetime | None = None) -> dict:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    fontes, ultimas, falta, atrasada = [], [], False, False
    nomes = {r[0] for r in con.execute("select distinct fonte from rodada")}
    nomes |= set(ESPERADAS)
    nomes.add("trabalho") if _trabalho_em_uso(con) else nomes.discard("trabalho")
    nomes.add("agenda") if _agenda_em_uso(con) else nomes.discard("agenda")
    nomes.add("correio") if _correio_em_uso(con) else nomes.discard("correio")
    nomes = sorted(n for n in nomes if not (n in FONTES and FONTES[n] is None))
    for nome in nomes:
        conta = FONTES.get(nome) is not None
        tent = con.execute("select status, conferida from rodada where fonte=? order by id desc limit 1", (nome,)).fetchone()
        if nome in COM_CONFERENCIA:
            conf = con.execute("select max(fim) from rodada where fonte=? and conferida=1", (nome,)).fetchone()[0]
            ultima = _utc(conf) if conf else None
            if tent["status"] == "erro":
                estado = "erro"
            elif not tent["conferida"]:
                estado = "nao_conferida"
            elif ultima is None or agora - ultima > FONTES[nome]:
                estado = "parada"
            else:
                estado = "ok"
            # extrato com última tentativa em erro segue valendo pela última conferida até o limite (comportamento antigo, coberto por teste)
        else:
            ok = con.execute("select max(fim) from rodada where fonte=? and status='ok'", (nome,)).fetchone()[0]
            ultima = _utc(ok) if ok else None
            if tent is not None and tent["status"] == "erro":
                estado = "erro"
            elif ultima is None:
                estado = "nao_conferida"  # nunca rodou com sucesso (ou nunca rodou)
            elif conta and agora - ultima > FONTES[nome]:
                estado = "parada"
            else:
                estado = "ok"
            atrasada = atrasada or (conta and estado in ("erro", "parada"))
        if conta:
            if ultima is None:
                falta = True
            else:
                ultimas.append(ultima)
            atrasada = atrasada or (nome in COM_CONFERENCIA and estado == "parada")
        fontes.append({"nome": nome, "estado": estado, "ultima": _z(ultima) if ultima else None})
    dados_ate = None if (falta or not ultimas) else min(ultimas)  # a fonte mais velha manda
    return {"dados_ate": _z(dados_ate) if dados_ate else None,
            "desatualizado": dados_ate is None or atrasada or agora - dados_ate > LIMITE_DESATUALIZADO,
            "proxima_rodada": proxima_rodada(agora), "fontes": fontes, "dados": dados}
