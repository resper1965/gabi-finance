"""Formatação e relógio compartilhados pelos módulos de gabi/cobrar."""
import datetime as dt


def agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def brl(centavos: int) -> str:
    return f"R$ {centavos // 100:,}".replace(",", ".") + f",{centavos % 100:02d}"
