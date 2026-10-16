"""'Hoje' do Ricardo: sempre Brasília, nunca o relógio do servidor (que roda em CEST)."""
import datetime as dt
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")


def hoje_brt() -> dt.date:
    return dt.datetime.now(BRT).date()
