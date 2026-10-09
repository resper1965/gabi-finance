import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tools.marcar_padroes import marcar_origem_padrao

MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','CREDIT','sim')")
    c.execute("insert into pessoa(id, nome) values ('casa','Casa')")
    c.execute("insert into pessoa(id, nome) values ('ricardo','Ricardo')")
    return c


def _l(con, i, desc, dono, origem):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, para_quem_id, para_quem_origem, status) "
                "values (1,?,?,?,?,?,?,?, 'posted')", (f"l{i}", "2026-09-01", -1000, desc, desc, dono, origem))


def _origem(con, i):
    return con.execute("select para_quem_origem from lancamento where externo_id=?", (f"l{i}",)).fetchone()[0]


def test_regra_antiga_sem_regra_correspondente_vira_padrao_do_cadastro(con):
    _l(con, 1, "SUPERMERCADO X", "casa", "regra")          # veio de padrão (cartão/categoria), não de regra por estabelecimento
    _l(con, 2, "MERCADOLIVRE PROD", "casa", "regra")       # veio de regra por estabelecimento
    _l(con, 3, "OUTRA COISA", "ricardo", "voce")
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('MERCADOLIVRE', ?, 1, 'x', 'r')", (json.dumps({"para_quem_id": "casa"}),))
    n = marcar_origem_padrao(con)
    assert n == 1 and (_origem(con, 1), _origem(con, 2), _origem(con, 3)) == ("fonte", "regra", "voce")


def test_regra_inativa_ou_de_outro_campo_nao_protege(con):
    _l(con, 1, "LOJA A", "casa", "regra")
    _l(con, 2, "LOJA B", "casa", "regra")
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('LOJA A', ?, 0, 'x', 'r')", (json.dumps({"para_quem_id": "casa"}),))      # inativa
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('LOJA B', ?, 1, 'x', 'r')", (json.dumps({"categoria_id": 1}),))          # só categoria
    assert marcar_origem_padrao(con) == 2


def test_e_idempotente(con):
    _l(con, 1, "SUPERMERCADO X", "casa", "regra")
    assert marcar_origem_padrao(con) == 1 and marcar_origem_padrao(con) == 0
