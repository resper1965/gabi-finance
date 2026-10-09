import datetime as dt
import pathlib
import re

from gabi.envelope import HORAS_RODADAS, proxima_rodada

UTC = dt.timezone.utc


def test_proxima_rodada_antes_das_7_e_das_15_e_na_virada_do_dia():
    # 10:00 UTC = 07:00 BRT em ponto: a de 07h já passou, a próxima é 15h BRT = 18:00 UTC
    assert proxima_rodada(dt.datetime(2026, 10, 9, 10, 0, tzinfo=UTC)) == "2026-10-09T18:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 9, 59, tzinfo=UTC)) == "2026-10-09T10:00:00Z"
    # depois das 15h BRT: amanhã 07h BRT
    assert proxima_rodada(dt.datetime(2026, 10, 9, 18, 0, tzinfo=UTC)) == "2026-10-10T10:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 23, 30, tzinfo=UTC)) == "2026-10-10T10:00:00Z"


def test_horas_batem_com_o_timer_instalado():
    timer = (pathlib.Path(__file__).parent.parent / "deploy" / "gabi-brain-extratos.timer").read_text()
    horas = re.search(r"OnCalendar=\S+ (\d\d(?:,\d\d)*):00:00 America/Sao_Paulo", timer).group(1)
    assert tuple(int(h) for h in horas.split(",")) == HORAS_RODADAS
