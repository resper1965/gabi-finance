import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.projecao import projetar

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent.parent / "migrations"
_n = iter(range(1, 100000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','Itau','BANK','sim')")        # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('cc1','Itau','CREDIT','sim')")     # 2
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-10-16T08:00:00', 1000000)")
    return c


def comp(con, id_, venc, estado, valor, origem="linha"):
    con.execute("insert into compromisso(id, origem, nome, vencimento, valor_centavos, estado) values (?,?,?,?,?,?)", (id_, origem, id_, venc, valor, estado))


def nota(con, venc, liquido, status="autorizada", pago=0, tomador="X", doc="1"):
    i = next(_n)
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, tomador_doc, vencimento, valor_liquido_centavos, nibo_pago, importado_em, atualizado_em) "
                "values (?,?,?,?,?,?,?,?,?,?,'x','x')", (f"n{i}", str(i), venc, status, liquido, tomador, doc, venc, liquido, pago))


def dia(r, iso):
    return next(d for d in r if d["dia"] == iso)


def test_saldo_inicial_e_o_caixa_unico(con):
    r = projetar(con, HOJE, 3)
    assert [d["dia"] for d in r] == ["2026-10-16", "2026-10-17", "2026-10-18"]
    assert all(d["saldo_centavos"] == 1000000 and d["entradas_centavos"] == 0 and d["saidas_centavos"] == 0 for d in r)


def test_saida_de_fatura_aberta_entra_no_vencimento(con):
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','cc1','2026-10-20',250000,'OPEN',2)")
    r = projetar(con, HOJE, 7)
    assert dia(r, "2026-10-19")["saldo_centavos"] == 1000000 and dia(r, "2026-10-20")["saidas_centavos"] == 250000
    assert dia(r, "2026-10-22")["saldo_centavos"] == 750000


def test_fatura_que_ja_e_compromisso_nao_conta_duas_vezes(con):
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','cc1','2026-10-20',250000,'OPEN',2)")
    comp(con, "fatura:cc1:2026-10", "2026-10-20", "aberto", 250000, origem="fatura")
    assert dia(projetar(con, HOJE, 7), "2026-10-22")["saldo_centavos"] == 750000


def test_compromisso_pago_nao_reduz_o_saldo(con):
    comp(con, "a:2026-10", "2026-10-18", "pago", 500000)
    comp(con, "b:2026-10", "2026-10-18", "aberto", 100000)
    assert dia(projetar(con, HOJE, 5), "2026-10-18")["saidas_centavos"] == 100000


def test_compromisso_atrasado_sai_hoje_e_debito_automatico_sai_no_dia(con):
    comp(con, "a:2026-10", "2026-10-10", "atrasado", 40000)
    comp(con, "d:2026-10", "2026-10-22", "debito_automatico", 62900)
    r = projetar(con, HOJE, 10)
    assert dia(r, "2026-10-16")["saidas_centavos"] == 40000 and dia(r, "2026-10-22")["saidas_centavos"] == 62900


def test_compromisso_sem_valor_nao_inventa_saida(con):
    con.execute("insert into compromisso(id, origem, nome, vencimento, valor_centavos, estado) values ('v:2026-10','linha','v','2026-10-18',NULL,'aberto')")
    assert dia(projetar(con, HOJE, 5), "2026-10-18")["saidas_centavos"] == 0


def test_nota_a_vencer_entra_pelo_liquido_no_vencimento(con):
    nota(con, "2026-10-25", 2226122)
    r = projetar(con, HOJE, 12)
    assert dia(r, "2026-10-25")["entradas_centavos"] == 2226122 and dia(r, "2026-10-27")["saldo_centavos"] == 1000000 + 2226122


def test_nota_vencida_e_nao_baixada_nao_entra_como_entrada(con):
    nota(con, "2026-09-20", 999900)            # 26 dias de vencida: fila de conferência, não previsão
    nota(con, "2026-05-10", 500000)
    r = projetar(con, HOJE, 10)
    assert all(d["entradas_centavos"] == 0 for d in r)


def test_nota_ja_marcada_paga_no_nibo_ou_cancelada_nao_entra(con):
    nota(con, "2026-10-25", 111100, pago=1); nota(con, "2026-10-25", 222200, status="cancelada"); nota(con, "2026-10-25", 333300, status="negada")
    assert all(d["entradas_centavos"] == 0 for d in projetar(con, HOJE, 12))


def test_projecao_de_contrato_recorrente_entra_so_se_a_data_ainda_nao_passou(con):
    for mes in ("2026-07", "2026-08", "2026-09"):
        nota(con, f"{mes}-25", 100000, tomador="REC", doc="9")
    r = projetar(con, HOJE, 45)
    assert dia(r, "2026-10-25")["entradas_centavos"] == 100000 and dia(r, "2026-11-25")["entradas_centavos"] == 100000


def test_valor_em_centavos_inteiros(con):
    comp(con, "a:2026-10", "2026-10-18", "aberto", 33333)
    nota(con, "2026-10-19", 66667)
    assert all(isinstance(d[k], int) for d in projetar(con, HOJE, 5) for k in ("entradas_centavos", "saidas_centavos", "saldo_centavos"))


def test_horizonte_respeita_dias(con):
    comp(con, "longe:2026-12", "2026-12-30", "aberto", 90000)
    assert len(projetar(con, HOJE, 30)) == 30 and all(d["saidas_centavos"] == 0 for d in projetar(con, HOJE, 30))


def test_fatura_vencida_ha_mais_de_45_dias_e_nao_paga_nao_vira_saida_de_hoje(con):
    # real: Itaú Visa Infinite, fatura de 25/04/2026 de R$ 61.844,58 PAST_DUE_UNPAID (saldo financiado): histórico, não saída de hoje
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('velha','cc1','2026-04-25',6184458,'PAST_DUE_UNPAID',2)")
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('recente','cc1','2026-10-05',528055,'PAST_DUE_UNCONFIRMED',2)")
    r = projetar(con, HOJE, 3)
    assert dia(r, "2026-10-16")["saidas_centavos"] == 528055     # só a recente (vencida há 11 dias) conta


def test_fatura_reivindicada_por_linha_da_planilha_nao_conta_duas_vezes(con):
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','cc1','2026-10-20',250000,'OPEN',2)")
    con.execute("insert into compromisso(id, origem, nome, vencimento, valor_centavos, estado, dados) values (?,?,?,?,?,?,?)",
                ("cartao-itau:2026-10", "planilha", "Cartão Itaú", "2026-10-20", 250000, "aberto", '{"cartao_account_id": "cc1"}'))
    assert dia(projetar(con, HOJE, 7), "2026-10-22")["saldo_centavos"] == 750000


def test_compromisso_de_fatura_sem_valor_nao_esconde_a_fatura_real(con):
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','cc1','2026-10-20',250000,'OPEN',2)")
    con.execute("insert into compromisso(id, origem, nome, vencimento, valor_centavos, estado) values ('fatura:cc1:2026-10','fatura','F','2026-10-20',NULL,'aberto')")
    assert dia(projetar(con, HOJE, 7), "2026-10-22")["saldo_centavos"] == 750000
