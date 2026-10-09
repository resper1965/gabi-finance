import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.comprovantes import confirmar, propor_vinculos, registrar_comprovante, rejeitar, sem_comprovante
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','Itau','BANK','sim')")
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    return c


def _l(con, i, data, valor, desc="PAGAMENTO", empresa=None):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, status) "
                       "values (1,?,?,?,?,?,?, 'posted')", (f"l{i}", data, valor, desc, desc.split()[0], empresa)).lastrowid


def _comp(con, pid=1, valor=15000, data="2026-10-06", cnpj=None):
    return registrar_comprovante(con, paperless_id=pid, tipo="comprovante_pix", valor_centavos=valor, data=data, cnpj=cnpj)


def test_registrar_comprovante_e_idempotente_por_paperless_id(con):
    assert _comp(con) == _comp(con)
    assert con.execute("select count(*) from comprovante").fetchone()[0] == 1


def test_vinculo_exige_valor_igual(con):
    _l(con, 1, "2026-10-06", -15000)
    _l(con, 2, "2026-10-06", -14999)  # um centavo de diferença não casa
    vs = propor_vinculos(con, _comp(con))
    assert [v.lancamento_id for v in vs] == [1]


def test_vinculo_so_na_janela_de_3_dias(con):
    _l(con, 1, "2026-10-09", -15000)   # +3 dias: entra
    _l(con, 2, "2026-10-10", -15000)   # +4 dias: fora
    _l(con, 3, "2026-10-03", -15000)   # -3 dias: entra
    _l(con, 4, "2026-10-02", -15000)   # -4 dias: fora
    assert {v.lancamento_id for v in propor_vinculos(con, _comp(con))} == {1, 3}


def test_vinculo_proposto_nunca_vira_confirmado_sozinho(con):
    _l(con, 1, "2026-10-06", -15000)
    v = propor_vinculos(con, _comp(con))[0]
    assert v.estado == "proposto"
    assert con.execute("select count(*) from comprovante_vinculo where estado='confirmado'").fetchone()[0] == 0
    propor_vinculos(con, 1)  # repropor não confirma nem duplica
    assert con.execute("select estado from comprovante_vinculo").fetchall()[0][0] == "proposto"
    assert con.execute("select count(*) from comprovante_vinculo").fetchone()[0] == 1


def test_confianca_traz_motivo_e_cresce_com_data_exata_e_cnpj(con):
    _l(con, 1, "2026-10-06", -15000, desc="LOJA 11222333000181")
    _l(con, 2, "2026-10-08", -15000, desc="OUTRA")
    vs = {v.lancamento_id: v for v in propor_vinculos(con, _comp(con, cnpj="11222333000181"))}
    assert 0 < vs[2].confianca < vs[1].confianca <= 1
    assert "valor" in vs[2].motivo and "CNPJ" in vs[1].motivo and vs[1].motivo != vs[2].motivo


def test_so_saida_pode_ser_vinculada(con):
    _l(con, 1, "2026-10-06", 15000)  # entrada de mesmo valor
    assert propor_vinculos(con, _comp(con)) == []


def test_confirmar_e_rejeitar_registram_decisao_e_nao_se_repetem(con):
    _l(con, 1, "2026-10-06", -15000)
    v = propor_vinculos(con, _comp(con))[0]
    confirmar(con, v.id, "boss@x.com")
    assert con.execute("select estado from comprovante_vinculo where id=?", (v.id,)).fetchone()[0] == "confirmado"
    assert con.execute("select count(*) from decisao where origem='cobrar'").fetchone()[0] == 1
    with pytest.raises(ValueError):
        rejeitar(con, v.id, "boss@x.com")  # já decidido


def test_nao_propoe_lancamento_que_ja_tem_comprovante_confirmado(con):
    _l(con, 1, "2026-10-06", -15000)
    confirmar(con, propor_vinculos(con, _comp(con, pid=1))[0].id, "boss@x.com")
    assert propor_vinculos(con, _comp(con, pid=2)) == []


def test_sem_comprovante_lista_so_o_que_precisa(con):
    _l(con, 1, "2026-10-06", -15000, empresa="e1")        # despesa de empresa sem comprovante: precisa
    _l(con, 2, "2026-10-06", -9000)                        # sem empresa: não precisa
    _l(con, 3, "2026-10-06", -7000, empresa="e1")         # com comprovante confirmado: não precisa
    _l(con, 4, "2026-09-01", -5000, empresa="e1")         # antes de `desde`: não entra
    _l(con, 5, "2026-10-06", 20000, empresa="e1")         # entrada: não precisa
    confirmar(con, propor_vinculos(con, _comp(con, pid=9, valor=7000))[0].id, "boss@x.com")
    assert [x["id"] for x in sem_comprovante(con, dt.date(2026, 10, 1))] == [1]
