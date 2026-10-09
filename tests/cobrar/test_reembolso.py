from pathlib import Path

import pytest

from gabi.cobrar.reembolso import conciliar_recebimento, criar_reembolso, itens_a_reembolsar, marcar_cobrado
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")      # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj','C6','BANK','C6 PJ',1,'sim')")          # 2
    c.execute("insert into empresa(id, nome, relacao) values ('ness','Ness','contratante')")
    c.execute("insert into empresa(id, nome, relacao) values ('bekaa','Bekaa','pj_titular')")
    c.execute("insert into empresa(id, nome) values ('x','Sem relação')")
    return c


def _l(con, i, data, valor, conta=1, empresa=None, desc="DESPESA"):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, status) "
                       "values (?,?,?,?,?,?,?, 'posted')", (conta, f"l{i}", data, valor, desc, desc, empresa)).lastrowid


def _estado(con, rid):
    return con.execute("select estado from reembolso where id=?", (rid,)).fetchone()[0]


def test_itens_so_de_despesa_paga_no_pf_para_contratante(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")               # entra
    _l(con, 2, "2026-10-02", -5000, conta=2, empresa="ness")       # paga pela PJ: não é reembolso
    _l(con, 3, "2026-10-03", 7000, empresa="ness")                 # entrada: não
    _l(con, 4, "2026-10-04", -3000)                                # sem empresa: não
    assert [i.lancamento_id for i in itens_a_reembolsar(con, "ness")] == [1]


def test_bekaa_nao_gera_cobranca(con):
    _l(con, 1, "2026-10-01", -10000, empresa="bekaa")
    assert itens_a_reembolsar(con, "bekaa") == []
    with pytest.raises(ValueError, match="lote"):
        criar_reembolso(con, "bekaa")


def test_empresa_sem_relacao_definida_nao_gera_cobranca(con):
    _l(con, 1, "2026-10-01", -10000, empresa="x")
    assert itens_a_reembolsar(con, "x") == []


def test_estado_so_avanca_na_ordem(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = criar_reembolso(con, "ness")
    assert _estado(con, rid) == "a_cobrar"
    marcar_cobrado(con, rid)
    assert _estado(con, rid) == "cobrado"
    with pytest.raises(ValueError):
        marcar_cobrado(con, rid)  # já cobrado: não volta nem repete
    conciliar_recebimento(con, "ness", _l(con, 9, "2026-10-10", 4000, conta=2))
    assert _estado(con, rid) == "parcialmente_recebido"


def test_recebimento_antes_da_cobranca_nao_baixa_nada(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = criar_reembolso(con, "ness")  # ainda a_cobrar
    r = conciliar_recebimento(con, "ness", _l(con, 9, "2026-10-10", 10000, conta=2))
    assert r.casados == [] and r.sobra_centavos == 10000 and _estado(con, rid) == "a_cobrar"


def test_recebimento_parcial_deixa_resto_em_aberto(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = criar_reembolso(con, "ness"); marcar_cobrado(con, rid)
    r = conciliar_recebimento(con, "ness", _l(con, 9, "2026-10-10", 6000, conta=2))
    assert r.casados == [] and r.sobra_centavos == 0
    assert [(i.lancamento_id, i.em_aberto_centavos) for i in itens_a_reembolsar(con, "ness")] == [(1, 4000)]
    assert _estado(con, rid) == "parcialmente_recebido"


def test_baixa_casa_mais_antigo_primeiro_e_quita(con):
    _l(con, 1, "2026-10-05", -3000, empresa="ness")
    _l(con, 2, "2026-10-01", -5000, empresa="ness")   # mais antigo
    rid = criar_reembolso(con, "ness"); marcar_cobrado(con, rid)
    r = conciliar_recebimento(con, "ness", _l(con, 9, "2026-10-10", 5000, conta=2))
    assert r.casados == [2] and r.sobra_centavos == 0  # o de 01/10 quita primeiro
    r2 = conciliar_recebimento(con, "ness", _l(con, 10, "2026-10-11", 4000, conta=2))
    assert r2.casados == [1] and r2.sobra_centavos == 1000 and _estado(con, rid) == "quitado"


def test_o_mesmo_credito_nao_baixa_duas_vezes(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = criar_reembolso(con, "ness"); marcar_cobrado(con, rid)
    cred = _l(con, 9, "2026-10-10", 4000, conta=2)
    conciliar_recebimento(con, "ness", cred)
    r = conciliar_recebimento(con, "ness", cred)
    assert r.casados == [] and r.sobra_centavos == 0
    assert [i.em_aberto_centavos for i in itens_a_reembolsar(con, "ness")] == [6000]


def test_credito_precisa_ser_entrada_em_conta_pj(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = criar_reembolso(con, "ness"); marcar_cobrado(con, rid)
    with pytest.raises(ValueError):
        conciliar_recebimento(con, "ness", _l(con, 9, "2026-10-10", 4000, conta=1))   # entrada em conta PF
    with pytest.raises(ValueError):
        conciliar_recebimento(con, "ness", _l(con, 10, "2026-10-10", -4000, conta=2))  # saída
