"""Regra das horas úteis do Teams: seg–sex, dentro do expediente, em Brasília. Sem texto de mensagem."""
import datetime as dt
import json
import re

from gabi.hoje import BRT

EXPEDIENTE_PADRAO = (dt.time(8, 0), dt.time(19, 0))
HORAS_PADRAO = 2.0


def _dt(v) -> dt.datetime | None:
    if not v:
        return None
    if isinstance(v, str):
        v = dt.datetime.fromisoformat(v)
    if v.tzinfo is None:
        v = v.replace(tzinfo=dt.timezone.utc)
    return v


def horas_uteis_entre(inicio: dt.datetime, fim: dt.datetime, expediente) -> float:
    a, b = _dt(inicio).astimezone(BRT), _dt(fim).astimezone(BRT)
    if b <= a:
        return 0.0
    abre, fecha = expediente
    total = 0.0
    dia = a.date()
    while dia <= b.date():
        if dia.weekday() < 5:
            ini = max(a, dt.datetime.combine(dia, abre, tzinfo=BRT))
            f = min(b, dt.datetime.combine(dia, fecha, tzinfo=BRT))
            if f > ini:
                total += (f - ini).total_seconds() / 3600
        dia += dt.timedelta(days=1)
    return total


def pendente(conv, agora: dt.datetime, horas: float, expediente) -> bool:
    para_mim = _dt(conv["ultima_para_mim_em"])
    if para_mim is None:
        return False
    resp = _dt(conv["minha_ultima_resposta_em"])
    if resp is not None and resp >= para_mim:
        return False
    aviso = _dt(conv["ultimo_aviso_em"])
    if aviso is not None and aviso >= para_mim:
        return False
    return horas_uteis_entre(para_mim, agora, expediente) >= horas


def _parametro(con, chave: str):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    try:
        return json.loads(r[0]) if r else None
    except (ValueError, TypeError):
        return None


def ler_config(con):
    horas = _parametro(con, "teams.horas_uteis")
    if isinstance(horas, bool) or not isinstance(horas, (int, float)) or horas <= 0:
        horas = 2
    exp = EXPEDIENTE_PADRAO
    v = _parametro(con, "teams.expediente")
    m = re.fullmatch(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", v) if isinstance(v, str) else None
    if m:
        try:
            a, f = dt.time(int(m[1]), int(m[2])), dt.time(int(m[3]), int(m[4]))
            if a < f:
                exp = (a, f)
        except ValueError:
            pass
    return horas, exp
