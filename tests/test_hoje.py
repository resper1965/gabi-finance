import datetime as dt

from gabi import hoje as h


def test_hoje_e_data_de_brasilia_perto_da_meia_noite(monkeypatch):
    class Falso(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 17, 1, 30, tzinfo=dt.timezone.utc).astimezone(tz)  # 22:30 de 16/10 em Brasília
    monkeypatch.setattr(h.dt, "datetime", Falso)
    assert h.hoje_brt() == dt.date(2026, 10, 16)
