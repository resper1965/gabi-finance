import datetime as dt
import pathlib
import re

from gabi.envelope import HORAS_RODADAS, proxima_rodada

UTC = dt.timezone.utc


def test_proxima_rodada_antes_das_6_e_das_14_e_na_virada_do_dia():
    # 09:00 UTC = 06:00 BRT em ponto: a de 06h já passou, a próxima é 14h BRT = 17:00 UTC
    assert proxima_rodada(dt.datetime(2026, 10, 9, 9, 0, tzinfo=UTC)) == "2026-10-09T17:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 8, 59, tzinfo=UTC)) == "2026-10-09T09:00:00Z"
    # depois das 14h BRT: amanhã 06h BRT
    assert proxima_rodada(dt.datetime(2026, 10, 9, 17, 0, tzinfo=UTC)) == "2026-10-10T09:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 23, 30, tzinfo=UTC)) == "2026-10-10T09:00:00Z"


def test_horas_batem_com_o_timer_instalado():
    timer = (pathlib.Path(__file__).parent.parent / "deploy" / "gabi-brain-extratos.timer").read_text()
    horas = re.search(r"OnCalendar=\S+ (\d\d(?:,\d\d)*):00:00 America/Sao_Paulo", timer).group(1)
    assert tuple(int(h) for h in horas.split(",")) == HORAS_RODADAS
