"""Envelope de toda resposta de leitura: `dados_ate` vem da última rodada CONFERIDA, não da última tentativa (R4/Review 4)."""
import datetime as dt

IGNORADAS = ("backup", "importacao-staging", "open-finance-saldos")  # não são fontes que se "confere" (saldos têm rodada própria)
LIMITE_DESATUALIZADO = dt.timedelta(days=3)
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


def envelope(con, dados, agora: dt.datetime | None = None) -> dict:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    fontes, ultimas, falta = [], [], False
    nomes = [r[0] for r in con.execute(f"select distinct fonte from rodada where fonte not in ({','.join('?' * len(IGNORADAS))}) order by fonte", IGNORADAS)]
    for nome in nomes:
        conf = con.execute("select max(fim) from rodada where fonte=? and conferida=1", (nome,)).fetchone()[0]
        ultima = _utc(conf) if conf else None
        tent = con.execute("select status, conferida from rodada where fonte=? order by id desc limit 1", (nome,)).fetchone()
        if tent["status"] == "erro":
            estado = "erro"
        elif not tent["conferida"]:
            estado = "nao_conferida"
        elif ultima is None or agora - ultima > LIMITE_DESATUALIZADO:
            estado = "parada"
        else:
            estado = "ok"
        if ultima is None:
            falta = True
        else:
            ultimas.append(ultima)
        fontes.append({"nome": nome, "estado": estado, "ultima": _z(ultima) if ultima else None})
    dados_ate = None if (falta or not ultimas) else min(ultimas)  # a fonte mais velha manda
    return {"dados_ate": _z(dados_ate) if dados_ate else None,
            "desatualizado": dados_ate is None or agora - dados_ate > LIMITE_DESATUALIZADO,
            "proxima_rodada": proxima_rodada(agora), "fontes": fontes, "dados": dados}
