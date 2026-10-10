import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import consultas
from gabi.dinheiro.rumo import rumo_mensal

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Itau','BANK','Itaú','a_decidir')")
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    c.execute("insert into pessoa(id, nome) values ('p2','Bia')")
    return c


def _l(con, i, data, valor, nat, conta=1, pessoa=None, frente=None):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, natureza, para_quem_id, frente_id, descricao_original) values (?,?,?,?,?,?,?,'x')",
                (conta, f"l{i}", data, valor, nat, pessoa, frente))


def test_doze_meses_mesmo_sem_movimento(con):
    linhas = rumo_mensal(con, 2026)
    assert [l.mes for l in linhas] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert all(l.entradas == 0 and l.saidas == 0 and l.gasto == 0 for l in linhas)


def test_entradas_saidas_e_poupanca_do_mes(con):
    _l(con, 1, "2026-03-05", 500000, "caixa")
    _l(con, 2, "2026-03-10", -120000, "caixa+custo", pessoa="p1")
    _l(con, 3, "2026-03-12", -30000, "caixa")  # paga fatura: sai do caixa, não é custo
    m = rumo_mensal(con, 2026)[2]
    assert (m.entradas, m.saidas, m.poupanca, m.gasto) == (500000, 150000, 350000, 120000)


def test_rumo_soma_igual_ao_extrato(con):
    for i, (d, v, n) in enumerate([("2026-01-03", 100000, "caixa"), ("2026-01-20", -40000, "caixa+custo"), ("2026-06-02", 250000, "caixa"),
                                   ("2026-06-30", -90000, "caixa+custo"), ("2026-12-31", -10000, "caixa+custo"), ("2025-12-31", 99999, "caixa")]):
        _l(con, i, d, v, n)
    linhas = rumo_mensal(con, 2026)
    extrato = con.execute("select sum(valor_centavos) from lancamento where natureza like '%caixa%' and data>='2026-01-01' and data<='2026-12-31'").fetchone()[0]
    assert sum(l.poupanca for l in linhas) == extrato
    assert sum(l.gasto for l in linhas) == sum(r["gasto"] for r in consultas.custos(con, dt.date(2026, 1, 1), dt.date(2026, 12, 31)))


def test_conta_nao_liberada_fica_fora_do_caixa(con):
    _l(con, 1, "2026-03-05", 700000, "caixa", conta=2)
    assert rumo_mensal(con, 2026)[2].entradas == 0


def test_gasto_por_pessoa_e_por_frente(con):
    _l(con, 1, "2026-04-01", -1000, "caixa+custo", pessoa="p1", frente=7)
    _l(con, 2, "2026-04-02", -2500, "caixa+custo", pessoa="p2", frente=7)
    _l(con, 3, "2026-04-03", -400, "caixa+custo")
    m = rumo_mensal(con, 2026)[3]
    assert m.por_pessoa == {"p1": 1000, "p2": 2500, "(sem pessoa)": 400} and m.por_frente == {"7": 3500, "(sem frente)": 400}


def test_patrimonio_e_o_ultimo_saldo_das_contas_liberadas_ate_o_fim_do_mes(con):
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,'2026-03-10T10:00:00',1000), (1,'2026-03-31T10:00:00',1500), (1,'2026-05-02T10:00:00',9000), (2,'2026-03-10T10:00:00',77777)")
    ls = rumo_mensal(con, 2026)
    assert ls[1].patrimonio is None  # fevereiro: ainda sem nenhum saldo
    assert ls[2].patrimonio == 1500 and ls[3].patrimonio == 1500 and ls[4].patrimonio == 9000
