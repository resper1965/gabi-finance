import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import nao_gasto

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, titular) values (1,'b1','Itaú','BANK','itau','sim','RICARDO ESPER')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado) values (2,'c1','Itaú','CREDIT','MC Black','sim')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado) values (3,'c2','Bradesco','CREDIT','Platinum','sim')")
    c.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','c1','2026-10-20',486952,'PAID',2)")
    c.execute("insert into empresa(id, nome, cnpj, dados) values ('bekaa','Bekaa Tecnologia LTDA','28.811.817/0001-69', ?)",
              (json.dumps({"relacao": "pj_titular"}),))
    c.execute("insert into empresa(id, nome, cnpj, dados) values ('ness','NESS Processos e Tecnologia LTDA','72.027.097/0001-37', ?)",
              (json.dumps({"relacao": "contratante"}),))
    return c


def lanc(con, desc, valor, cat=None, data="2026-10-18", conta=1, natureza="caixa+custo"):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_banco, natureza, status) "
                       "values (?,?,?,?,?,?,?, 'posted')", (conta, f"x{desc}{valor}{data}", data, valor, desc, cat, natureza)).lastrowid


def nat(con, lid):
    return tuple(con.execute("select natureza, natureza_regra from lancamento where id=?", (lid,)).fetchone())


def test_boleto_que_bate_com_fatura_nao_e_gasto(con):
    lid = lanc(con, "Pagamento de boleto ITAU UNIBANCO HOLDING S.A.", -486969, "Transfer - Bank Slip")  # R$ 0,17 de diferença
    nao_gasto.reaplicar(con)
    assert nat(con, lid) == ("caixa", "fatura")


def test_boleto_ao_emissor_de_cartao_sem_fatura_conhecida_nao_e_gasto(con):
    a = lanc(con, "Pagamento de boleto BANCO BRADESCO S.A.", -83144, "Investments", data="2025-09-04")
    b = lanc(con, "Pagamento de boleto INT PERSON VS", -1698333, "Transfer - Bank Slip", data="2025-09-25")
    nao_gasto.reaplicar(con)
    assert nat(con, a) == ("caixa", "emissor") and nat(con, b) == ("caixa", "emissor")


def test_boleto_de_escola_ou_condominio_segue_gasto(con):
    a = lanc(con, "Pagamento de boleto AVENUES SAO PAULO EDUCACAO LTD", -976667, "Transfer - Bank Slip")
    b = lanc(con, "Pagamento de boleto EDIFICIO VILLA DEI FIORI", -314100, "Housing")
    nao_gasto.reaplicar(con)
    assert nat(con, a) == ("caixa+custo", None) and nat(con, b) == ("caixa+custo", None)


def test_pix_para_empresa_propria_nao_e_gasto_e_para_contratante_e(con):
    a = lanc(con, "Pix enviado BEKAA TECNOLOGIA LTDA", -500000, "Transfer - PIX")
    b = lanc(con, "Pix enviado 28811817000169", -30000, "Transfer - PIX")
    c = lanc(con, "Pix enviado NESS PROCESSOS E TECNOLOGIA", -10000, "Transfer - PIX")
    d = lanc(con, "Google Workspace_bekaa", -16300, "Services")  # compra para a Bekaa (reembolso), não transferência
    nao_gasto.reaplicar(con)
    assert nat(con, a) == ("caixa", "propria") and nat(con, b) == ("caixa", "propria")
    assert nat(con, c) == ("caixa+custo", None) and nat(con, d) == ("caixa+custo", None)


def test_investimento_nao_e_gasto(con):
    ids = [lanc(con, "Transferência enviada para conta investimento", -56748300, "Transfers"),
           lanc(con, "APLICAÇÃO DE CDB", -3500000, "Investments"),
           lanc(con, "CHAMADA DE MARGEM", -121100, None)]
    nao_gasto.reaplicar(con)
    assert [nat(con, i) for i in ids] == [("caixa", "investimento")] * 3


def test_marcacao_manual_vence_a_regra_e_volta_ao_tirar(con):
    lid = lanc(con, "Pagamento de boleto BANCO SANTANDER BRASIL S A", -16985190, "Transfer - Bank Slip")
    con.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado) values (4,'c3','Santander','CREDIT','Elite','sim')")
    nao_gasto.reaplicar(con)
    assert nat(con, lid) == ("caixa", "emissor")
    con.execute("update lancamento set natureza_manual='gasto' where id=?", (lid,))
    nao_gasto.reaplicar(con, [lid])
    assert nat(con, lid) == ("caixa+custo", "manual")
    con.execute("update lancamento set natureza_manual=null where id=?", (lid,))
    nao_gasto.reaplicar(con, [lid])
    assert nat(con, lid) == ("caixa", "emissor")


def test_nao_gasto_manual_em_compra_de_cartao(con):
    lid = lanc(con, "LOJA X", -5000, conta=2, natureza="custo")
    con.execute("update lancamento set natureza_manual='nao_gasto' where id=?", (lid,))
    nao_gasto.reaplicar(con, [lid])
    assert nat(con, lid) == ("neutro", "manual")


def test_entrada_e_cartao_nao_mudam_e_e_idempotente(con):
    e = lanc(con, "Pix recebido BEKAA TECNOLOGIA LTDA", 900000, "Transfer - PIX", natureza="caixa")
    k = lanc(con, "Pagamento de boleto ITAU", -486952, conta=2, natureza="custo")
    assert nao_gasto.reaplicar(con) == {}
    assert nat(con, e) == ("caixa", None) and nat(con, k) == ("custo", None)
    assert nao_gasto.reaplicar(con) == {}
