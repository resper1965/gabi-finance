import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.previsao import previsao
from gabi.cobrar.recebimentos import confirmar_recebimento, propor_recebimentos, rejeitar_recebimento
from gabi.db import conectar, migrar

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent.parent / "migrations"
_n = iter(range(1, 100000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj','C6','BANK','C6 PJ',1,'sim')")   # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")  # 2
    return c


def nota(con, liquido=366015, venc="2026-10-15", status="autorizada", tomador="BARRA DO PARA TRANSPORTES", doc="01834520000162", emissao="2026-10-01"):
    i = next(_n)
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, tomador_doc, vencimento, valor_liquido_centavos, importado_em, atualizado_em) "
                "values (?,?,?,?,?,?,?,?,?,'x','x')", (f"n{i}", str(i), emissao, status, liquido + 10000, tomador, doc, venc, liquido))
    return f"n{i}"


def credito(con, valor=366015, data="2026-10-14", conta=1, desc="Pix recebido BARRA DO PARA TRANSPORTES"):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (?,?,?,?,?, 'posted')", (conta, f"c{next(_n)}", data, valor, desc))
    return con.execute("select max(id) from lancamento").fetchone()[0]


def propostas(con):
    return [dict(r) for r in con.execute("select * from recebimento_nota order by id")]


def test_propoe_credito_com_valor_liquido_igual(con):
    n, l = nota(con), credito(con)
    assert propor_recebimentos(con) == 1
    p = propostas(con)[0]
    assert (p["nota_id"], p["lancamento_id"], p["estado"]) == (n, l, "proposto") and p["confianca"] == 1.0 and "valor igual" in p["motivo"]


def test_sem_nome_nem_cnpj_e_com_data_longe_a_confianca_cai_mas_ainda_propoe(con):
    nota(con); credito(con, data="2026-10-02", desc="TED RECEBIDA")
    propor_recebimentos(con)
    assert propostas(con)[0]["confianca"] == 0.5


def test_nunca_vira_confirmado_sozinho(con):
    nota(con); credito(con)
    propor_recebimentos(con); propor_recebimentos(con)
    assert [p["estado"] for p in propostas(con)] == ["proposto"]


def test_nao_propoe_para_nota_negada_ou_cancelada(con):
    nota(con, status="negada"); nota(con, status="cancelada"); credito(con)
    assert propor_recebimentos(con) == 0


def test_credito_em_conta_pessoal_ou_de_valor_diferente_nao_casa(con):
    nota(con); credito(con, conta=2); credito(con, valor=366016)
    assert propor_recebimentos(con) == 0


def test_dois_creditos_iguais_geram_duas_propostas_sem_duplicar(con):
    nota(con); credito(con); credito(con, data="2026-10-16")
    assert propor_recebimentos(con) == 2 and propor_recebimentos(con) == 0
    assert len(propostas(con)) == 2


def test_confirmar_rejeita_as_outras_propostas_da_nota_e_do_credito(con):
    n1, n2 = nota(con), nota(con)                                   # duas notas do mesmo valor
    l1, l2 = credito(con), credito(con, data="2026-10-16")
    propor_recebimentos(con)                                        # 2 notas x 2 créditos = 4 propostas
    alvo = next(p["id"] for p in propostas(con) if (p["nota_id"], p["lancamento_id"]) == (n1, l1))
    confirmar_recebimento(con, alvo, "ricardo")
    estados = {(p["nota_id"], p["lancamento_id"]): p["estado"] for p in propostas(con)}
    assert estados[(n1, l1)] == "confirmado" and estados[(n1, l2)] == "rejeitado" and estados[(n2, l1)] == "rejeitado" and estados[(n2, l2)] == "proposto"


def test_credito_ja_confirmado_para_outra_nota_nao_e_proposto_de_novo(con):
    n1 = nota(con); l1 = credito(con)
    propor_recebimentos(con)
    confirmar_recebimento(con, propostas(con)[0]["id"], "ricardo")
    nota(con)                                                        # nova nota do mesmo valor
    assert propor_recebimentos(con) == 0


def test_rejeitar_nao_volta_a_propor_o_mesmo_par(con):
    nota(con); credito(con)
    propor_recebimentos(con)
    rejeitar_recebimento(con, propostas(con)[0]["id"], "ricardo")
    assert propor_recebimentos(con) == 0 and propostas(con)[0]["estado"] == "rejeitado"


def test_confirmar_exige_proposta_pendente_e_audita(con):
    nota(con); credito(con)
    propor_recebimentos(con)
    rid = propostas(con)[0]["id"]
    confirmar_recebimento(con, rid, "ricardo")
    with pytest.raises(ValueError):
        confirmar_recebimento(con, rid, "ricardo")
    assert con.execute("select count(*) from decisao where quem='ricardo' and o_que like '%recebimento%'").fetchone()[0] == 1


def test_nota_com_recebimento_confirmado_sai_da_previsao(con):
    n = nota(con, venc="2026-10-25"); credito(con, data="2026-10-24")
    assert previsao(con, HOJE, 1, projetar=False)["meses"][0]["a_vencer"]["qtd"] == 1
    propor_recebimentos(con)
    confirmar_recebimento(con, propostas(con)[0]["id"], "ricardo")
    assert previsao(con, HOJE, 1, projetar=False)["meses"][0]["a_vencer"]["qtd"] == 0
