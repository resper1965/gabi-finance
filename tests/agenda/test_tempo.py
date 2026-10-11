import pytest

from gabi.agenda import tempo

BRT = "America/Sao_Paulo"


def _h(inicio, fim, fuso=BRT):
    return tempo.de_google({"dateTime": inicio}, {"dateTime": fim}, fuso)


def _d(inicio, fim, fuso=BRT):
    return tempo.de_google({"date": inicio}, {"date": fim}, fuso)


def test_evento_das_22h_brt_cai_no_dia_local_certo():
    j = _h("2026-10-12T22:30:00-03:00", "2026-10-12T23:30:00-03:00")
    assert j.dia_local == "2026-10-12" and j.dia_fim_local == "2026-10-12"
    assert j.inicio_utc == "2026-10-13T01:30:00+00:00" and j.fim_utc == "2026-10-13T02:30:00+00:00"
    assert j.dia_inteiro is False


def test_evento_que_cruza_meia_noite_cobre_dois_dias():
    j = _h("2026-10-12T23:00:00-03:00", "2026-10-13T01:00:00-03:00")
    assert tempo.dias_do_evento(j) == ["2026-10-12", "2026-10-13"]


def test_evento_que_termina_na_meia_noite_exata_nao_invade_o_dia_seguinte():
    j = _h("2026-10-12T22:00:00-03:00", "2026-10-13T00:00:00-03:00")
    assert tempo.dias_do_evento(j) == ["2026-10-12"]


def test_dia_inteiro_fim_exclusivo_vira_ultimo_dia():
    um = _d("2026-10-12", "2026-10-13")
    assert um.dia_inteiro is True and tempo.dias_do_evento(um) == ["2026-10-12"]
    tres = _d("2026-10-12", "2026-10-15")
    assert tempo.dias_do_evento(tres) == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert tres.inicio_utc == "2026-10-12T03:00:00+00:00" and tres.fim_utc == "2026-10-15T03:00:00+00:00"


def test_dia_inteiro_nao_se_sobrepoe_a_horario():
    dia = _d("2026-10-12", "2026-10-13")
    horario = _h("2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00")
    assert tempo.se_sobrepoem(dia, horario) is False
    assert tempo.se_sobrepoem(horario, dia) is False
    assert tempo.se_sobrepoem(dia, dia) is False


def test_dois_horarios_se_sobrepoem_por_instante_com_offsets_diferentes():
    a = _h("2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00")  # 13:00–14:00 UTC
    b = _h("2026-10-12T13:30:00+00:00", "2026-10-12T14:30:00+00:00")
    colado = _h("2026-10-12T14:00:00+00:00", "2026-10-12T15:00:00+00:00")
    assert tempo.se_sobrepoem(a, b) is True
    assert tempo.se_sobrepoem(a, colado) is False  # encostar não é conflito


def test_fuso_configuravel():
    j = _h("2026-10-12T22:30:00-03:00", "2026-10-12T23:30:00-03:00", fuso="Europe/Berlin")
    assert j.dia_local == "2026-10-13"  # 01:30 em Berlim (UTC+2 nessa data)


def test_datetime_sem_offset_usa_o_fuso_configurado_ou_o_timezone_do_evento():
    sem = tempo.de_google({"dateTime": "2026-10-12T10:00:00"}, {"dateTime": "2026-10-12T11:00:00"}, BRT)
    assert sem.inicio_utc == "2026-10-12T13:00:00+00:00"
    com = tempo.de_google({"dateTime": "2026-10-12T10:00:00", "timeZone": "Europe/Berlin"},
                          {"dateTime": "2026-10-12T11:00:00", "timeZone": "Europe/Berlin"}, BRT)
    assert com.inicio_utc == "2026-10-12T08:00:00+00:00"


def test_z_e_offsets_diferentes_do_mesmo_instante_normalizam_igual():
    a = _h("2026-10-12T13:00:00Z", "2026-10-12T14:00:00Z")
    b = _h("2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00")
    c = _h("2026-10-12T15:00:00+02:00", "2026-10-12T16:00:00+02:00")
    assert a.inicio_utc == b.inicio_utc == c.inicio_utc == "2026-10-12T13:00:00+00:00"


@pytest.mark.parametrize("ini,fim", [
    ({"date": "2026-13-45"}, {"date": "2026-13-46"}),
    ({}, {}),
    ({"dateTime": "abc"}, {"dateTime": "def"}),
    ({"dateTime": "2026-10-12T10:00:00-03:00"}, {"date": "2026-10-13"}),  # mistura horário e dia inteiro
    ({"dateTime": "2026-10-12T11:00:00-03:00"}, {"dateTime": "2026-10-12T10:00:00-03:00"}),  # fim antes do início
    ({"date": "2026-10-12"}, {"date": "2026-10-11"}),
])
def test_dado_invalido_levanta_value_error(ini, fim):
    with pytest.raises(ValueError):
        tempo.de_google(ini, fim, BRT)


def test_fuso_invalido_levanta_value_error():
    with pytest.raises(ValueError):
        _h("2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", fuso="Marte/Olympus")


def test_hhmm_em_local():
    assert tempo.hhmm("2026-10-13T01:30:00+00:00", BRT) == "22:30"
    assert tempo.para_local("2026-10-13T01:30:00+00:00", BRT).day == 12
