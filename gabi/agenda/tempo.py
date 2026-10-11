"""Tempo da agenda: instante em UTC, dia local pré-calculado e dia inteiro (spec 2026-10-11-agenda-design, §3.4).
Nenhuma consulta nem tela fatia texto de data/hora: tudo converte do UTC para o fuso configurado (`parametro agenda.fuso`).
Dia inteiro do Google tem `fim` EXCLUSIVO: o último dia é fim−1. Evento horário que termina à meia-noite local não invade o dia seguinte."""
import datetime as dt
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = dt.timezone.utc
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Janela:
    inicio_utc: str
    fim_utc: str
    dia_local: str
    dia_fim_local: str
    dia_inteiro: bool


def _zona(nome: str) -> ZoneInfo:
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, KeyError, TypeError):
        raise ValueError("fuso inválido") from None


def _iso(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _instante(campo: dict, padrao: ZoneInfo) -> dt.datetime:
    texto = campo.get("dateTime")
    if not isinstance(texto, str):
        raise ValueError("dateTime ausente")
    try:
        d = dt.datetime.fromisoformat(texto)
        if d.tzinfo is None:  # sem offset: vale o timeZone do evento, senão o fuso configurado
            tz = campo.get("timeZone")
            d = d.replace(tzinfo=_zona(tz) if isinstance(tz, str) and tz else padrao)
    except (ValueError, TypeError):
        raise ValueError("dateTime inválido") from None
    return d


def _dia(campo: dict) -> dt.date:
    texto = campo.get("date")
    if not isinstance(texto, str) or not _DATA.match(texto):
        raise ValueError("date inválida")
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        raise ValueError("date inválida") from None


def de_google(inicio: dict, fim: dict, fuso: str) -> Janela:
    """Converte `start`/`end` do Google Calendar. Dado inválido levanta ValueError (quem chama pula o evento e conta)."""
    zona = _zona(fuso)
    if not isinstance(inicio, dict) or not isinstance(fim, dict):
        raise ValueError("start/end inválidos")
    if "date" in inicio or "date" in fim:
        if "dateTime" in inicio or "dateTime" in fim:
            raise ValueError("mistura de dia inteiro e horário")
        d1, d2 = _dia(inicio), _dia(fim)
        if d2 <= d1:
            raise ValueError("fim do dia inteiro não é posterior ao início")
        meia = dt.time(0, 0)
        return Janela(_iso(dt.datetime.combine(d1, meia, zona)), _iso(dt.datetime.combine(d2, meia, zona)),
                      d1.isoformat(), (d2 - dt.timedelta(days=1)).isoformat(), True)
    i, f = _instante(inicio, zona), _instante(fim, zona)
    if f < i:
        raise ValueError("fim antes do início")
    fim_local = f.astimezone(zona)
    ultimo = fim_local.date()
    if fim_local.time() == dt.time(0, 0) and f > i:
        ultimo -= dt.timedelta(days=1)
    return Janela(_iso(i), _iso(f), i.astimezone(zona).date().isoformat(), ultimo.isoformat(), False)


def para_local(instante_utc: str, fuso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(instante_utc).astimezone(_zona(fuso))


def hhmm(instante_utc: str, fuso: str) -> str:
    return para_local(instante_utc, fuso).strftime("%H:%M")


def dias_do_evento(j: Janela) -> list[str]:
    d, ultimo = dt.date.fromisoformat(j.dia_local), dt.date.fromisoformat(j.dia_fim_local)
    saida = [d.isoformat()]
    while d < ultimo:
        d += dt.timedelta(days=1)
        saida.append(d.isoformat())
    return saida


def se_sobrepoem(a: Janela, b: Janela) -> bool:
    """Sobreposição por instante. Dia inteiro nunca conflita com horário (nem com outro dia inteiro); encostar não é conflito."""
    if a.dia_inteiro or b.dia_inteiro:
        return False
    iso = dt.datetime.fromisoformat
    return iso(a.inicio_utc) < iso(b.fim_utc) and iso(b.inicio_utc) < iso(a.fim_utc)
