import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.hoje import BRT
from gabi.teams.regra import horas_uteis_entre, ler_config, pendente

EXP = (dt.time(8, 0), dt.time(19, 0))


def b(dia, h, m=0):
    return dt.datetime(2026, 10, dia, h, m, tzinfo=BRT)  # 19/10/2026 = segunda


def test_dentro_do_expediente_conta_o_tempo_corrido():
    assert horas_uteis_entre(b(19, 9), b(19, 11), EXP) == 2.0


def test_noite_nao_conta():
    assert horas_uteis_entre(b(19, 18), b(20, 9), EXP) == 2.0
    assert horas_uteis_entre(b(19, 18), b(20, 10), EXP) == 3.0


def test_fim_de_semana_nao_conta():
    assert horas_uteis_entre(b(16, 18), b(19, 9), EXP) == 2.0  # sexta 16 -> segunda 19


def test_aceita_utc():
    a = b(19, 9).astimezone(dt.timezone.utc)
    assert horas_uteis_entre(a, b(19, 11), EXP) == 2.0


def conv(**k):
    base = {"ultima_para_mim_em": b(19, 9).isoformat(), "minha_ultima_resposta_em": None, "ultimo_aviso_em": None}
    base.update(k)
    return base


def test_pendente_depois_de_duas_horas_uteis():
    assert pendente(conv(), b(19, 11), 2, EXP)
    assert not pendente(conv(), b(19, 10, 59), 2, EXP)
    assert not pendente(conv(ultima_para_mim_em=None), b(19, 18), 2, EXP)


def test_resposta_posterior_nao_e_pendente():
    assert not pendente(conv(minha_ultima_resposta_em=b(19, 9, 30).isoformat()), b(19, 18), 2, EXP)
    assert pendente(conv(minha_ultima_resposta_em=b(19, 8, 30).isoformat()), b(19, 18), 2, EXP)


def test_aviso_ja_enviado_para_a_mesma_mensagem_nao_repete():
    assert not pendente(conv(ultimo_aviso_em=b(19, 11).isoformat()), b(19, 18), 2, EXP)


def test_nova_mensagem_depois_do_aviso_volta_a_ser_pendente():
    c = conv(ultima_para_mim_em=b(19, 14).isoformat(), ultimo_aviso_em=b(19, 11).isoformat())
    assert pendente(c, b(19, 17), 2, EXP)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    return c


def test_config_padrao_e_parametros(con):
    assert ler_config(con) == (2, EXP)
    con.execute("insert into parametro(chave, valor) values ('teams.horas_uteis','3'),('teams.expediente',?)", (json.dumps("09:00-18:30"),))
    assert ler_config(con) == (3, (dt.time(9), dt.time(18, 30)))


def test_config_invalida_cai_no_padrao(con):
    con.execute("insert into parametro(chave, valor) values ('teams.horas_uteis','-1'),('teams.expediente',?)", (json.dumps("lixo"),))
    assert ler_config(con) == (2, EXP)


def test_inicio_as_23h_conta_so_do_proximo_dia_util():
    assert horas_uteis_entre(b(19, 23), b(20, 10), EXP) == 2.0
    assert horas_uteis_entre(b(16, 23), b(19, 10), EXP) == 2.0  # sexta 23:00 -> segunda 10:00


def test_inicio_no_sabado_e_antes_das_8():
    assert horas_uteis_entre(b(17, 10), b(19, 10), EXP) == 2.0  # sábado 17/10
    assert horas_uteis_entre(b(19, 5), b(19, 10), EXP) == 2.0


def test_inicio_igual_ou_depois_do_fim_da_zero():
    assert horas_uteis_entre(b(19, 10), b(19, 10), EXP) == 0.0
    assert horas_uteis_entre(b(19, 12), b(19, 10), EXP) == 0.0
