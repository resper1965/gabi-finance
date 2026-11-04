import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.decisoes import responder
from gabi.dinheiro.sugestoes_agenda import candidatas, propor

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent.parent / "migrations"
T = "2026-10-16T12:00:00+00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into agenda_fonte(id, conta, provedor, calendario_id, nome, estado, auth) values (1,'x','google','c','Cal','sim','oauth')")
    return c


def ev(con, titulo, dias, status="confirmed"):
    for i, d in enumerate(dias):
        con.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, status) "
                    "values (1,?,?,?,?,?,1,?,?)", (f"{titulo}{i}", d + "T03:00:00Z", d + "T04:00:00Z", d, d, titulo, status))


MENSAL = ["2026-10-20", "2026-11-20", "2026-12-20"]


def test_evento_mensal_de_pagar_no_mesmo_dia_vira_candidata(con):
    ev(con, "Pagar Seguro do Carro", MENSAL)
    assert candidatas(con, HOJE) == [{"titulo": "Pagar Seguro do Carro", "dia": 20, "meses": 3}]


def test_evento_unico_ou_sem_palavra_de_pagamento_nao_e_candidata(con):
    ev(con, "Pagar IPTU", ["2026-10-20"])
    ev(con, "Reunião de pais", MENSAL)
    assert candidatas(con, HOJE) == []


def test_dia_que_muda_de_mes_para_mes_nao_e_candidata(con):
    ev(con, "Pagar Colégio", ["2026-10-20", "2026-11-22"])
    assert candidatas(con, HOJE) == []


def test_fatura_de_cartao_nao_e_sugerida(con):
    ev(con, "Pagar Cartão de Credito - MASTERCARD BLACK", MENSAL)
    assert candidatas(con, HOJE) == []


def test_evento_cancelado_ou_passado_nao_conta(con):
    ev(con, "Pagar Jardineiro", MENSAL, status="cancelled")
    ev(con, "Pagar Piscina", ["2026-08-20", "2026-09-20"])
    assert candidatas(con, HOJE) == []


def test_o_que_ja_e_compromisso_nao_e_sugerido(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, apelidos, vencimento, ajuste_dia_util, valor_tipo, forma) "
                "values ('sirlene-adiantamento','Sirlene (adiantamento)','Pix enviado SIRLENE','[]','dia:20','adia','fixo','pix')")
    ev(con, "Adiantamento Sirlene", MENSAL)
    assert candidatas(con, HOJE) == []


def test_propor_cria_uma_pergunta_so_uma_vez(con):
    ev(con, "Pagar Seguro do Carro", MENSAL)
    assert propor(con, HOJE, T) == 1 and propor(con, HOJE, T) == 0
    assert con.execute("select count(*) from pergunta where tipo='compromisso_agenda'").fetchone()[0] == 1


def test_responder_1_cria_o_compromisso_e_responder_2_nao(con):
    ev(con, "Pagar Seguro do Carro", MENSAL)
    ev(con, "Pagar Jardim", ["2026-11-10", "2026-12-10"])
    propor(con, HOJE, T)
    p1, p2 = [r[0] for r in con.execute("select id from pergunta order by titulo")]  # Jardim, Seguro (ordem alfabética)
    responder(con, p1, 2, "ricardo", T)
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == 0
    responder(con, p2, 1, "ricardo", T)
    r = con.execute("select nome, vencimento, valor_tipo, obs, ativo from compromisso_linha").fetchall()
    assert [tuple(x) for x in r][0][:3] == ("Pagar Seguro do Carro", "dia:20", "variavel") and "agenda" in r[0]["obs"]
    assert r[0]["ativo"] == 0  # desativado até o Ricardo completar


def test_calendario_nao_liberado_e_evento_privado_nao_geram_sugestao(con):
    con.execute("insert into agenda_fonte(id, conta, provedor, calendario_id, nome, estado, auth) values (2,'x','google','d','Outro','a_decidir','oauth')")
    con.execute("update agenda_fonte set estado='sim' where id=1")
    for i, d in enumerate(MENSAL):
        con.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, status) "
                    "values (2,?,?,?,?,?,1,'Pagar Algo',  'confirmed')", (f"n{i}", d, d, d, d))
    ev(con, "Pagar Segredo", MENSAL)
    con.execute("update agenda_evento set privado=1 where titulo='Pagar Segredo'")
    assert candidatas(con, HOJE) == []
