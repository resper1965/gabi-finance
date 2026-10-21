from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.despesas_empresa import despesas_por_empresa

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into empresa(id, nome) values ('ness','NESS'), ('ionic','IONIC')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, pj) values (1,'pf','Itau','BANK','Itaú PF','sim',0)")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, pj) values (2,'pj','C6','BANK','C6 PJ','sim',1)")
    return c


def _l(con, i, data, valor, empresa, conta=1):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, natureza, empresa_id, descricao_original) values (?,?,?,?,'custo',?,?)",
                (conta, f"l{i}", data, valor, empresa, f"desc {i}"))


def test_agrupa_por_empresa_do_maior_para_o_menor(con):
    _l(con, 1, "2026-10-03", -10000, "ness")
    _l(con, 2, "2026-10-05", -5000, "ness")
    _l(con, 3, "2026-10-07", -30000, "ionic")
    r = despesas_por_empresa(con, "2026-10")
    assert [(e["empresa_id"], e["empresa"], e["total_centavos"]) for e in r] == [("ionic", "IONIC", 30000), ("ness", "NESS", 15000)]
    assert r[1]["itens"] == [{"lancamento_id": 1, "data": "2026-10-03", "descricao": "desc 1", "valor_centavos": 10000},
                             {"lancamento_id": 2, "data": "2026-10-05", "descricao": "desc 2", "valor_centavos": 5000}]


def test_ignora_conta_pj_entrada_sem_empresa_e_outro_mes(con):
    _l(con, 1, "2026-10-03", -10000, "ness", conta=2)   # pago pela PJ: não é reembolso
    _l(con, 2, "2026-10-03", 10000, "ness")             # entrada
    _l(con, 3, "2026-10-03", -10000, None)              # sem empresa
    _l(con, 4, "2026-09-30", -10000, "ness")            # outro mês
    _l(con, 5, "2026-11-01", -10000, "ness")            # outro mês
    assert despesas_por_empresa(con, "2026-10") == []


def test_conta_excluida_nao_entra(con):
    con.execute("update conta set excluido_em='2026-10-01' where id=1")
    _l(con, 1, "2026-10-03", -10000, "ness")
    assert despesas_por_empresa(con, "2026-10") == []


@pytest.mark.parametrize("mes", ["2026-13", "202610", "outubro", "", None])
def test_mes_invalido(con, mes):
    with pytest.raises(ValueError):
        despesas_por_empresa(con, mes)
