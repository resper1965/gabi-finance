import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.reembolso_saude import requisitos

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGR)
    return c


def _grava(con, d):
    con.execute("insert into parametro(chave, valor) values (?,?) on conflict(chave) do update set valor=excluded.valor",
                (requisitos.CHAVE, json.dumps(d)))


def test_sem_parametro_vale_o_seed(con):
    r = requisitos.carregar(con)
    assert r["operadora"] == "SulAmérica" and r["dias_guarda_nao_reembolsavel"] == 90
    assert r["consulta_exige"] == ["nf"] and r["tratamento_exige"] == ["nf", "autorizacao"]


def test_parametro_editado_manda_sobre_o_seed(con):
    d = requisitos.carregar(con)
    d["consulta_exige"] = ["nf", "autorizacao"]
    d["dias_sem_credito"] = 45
    _grava(con, d)
    r = requisitos.carregar(con)
    assert r["consulta_exige"] == ["nf", "autorizacao"] and r["dias_sem_credito"] == 45


def test_item_desconhecido_e_invalido(con):
    d = requisitos.carregar(con)
    d["todos"].append("carimbo")
    _grava(con, d)
    with pytest.raises(requisitos.RequisitosInvalidos, match="carimbo"):
        requisitos.carregar(con)


@pytest.mark.parametrize("campo,valor", [("dias_guarda_nao_reembolsavel", 0), ("dias_sem_credito", True), ("operadora", " "),
                                          ("consulta_exige", "nf"), ("tratamento", ["nf", 3])])
def test_valores_invalidos(con, campo, valor):
    d = requisitos.carregar(con)
    d[campo] = valor
    _grava(con, d)
    with pytest.raises(requisitos.RequisitosInvalidos):
        requisitos.carregar(con)


def test_json_quebrado_e_invalido(con):
    con.execute("insert into parametro(chave, valor) values (?, '{quebrado')", (requisitos.CHAVE,))
    with pytest.raises(requisitos.RequisitosInvalidos):
        requisitos.carregar(con)


def test_rotulo_usa_o_editado_e_cai_no_nome_do_item(con):
    r = requisitos.carregar(con)
    assert requisitos.rotulo(r, "nf") == "nota fiscal" and requisitos.rotulo(r, "doc_prestador") == "CPF/CNPJ do profissional"
    assert requisitos.rotulo(r, "pedido_medico") == "pedido médico" and requisitos.rotulo(r, "relatorio") == "relatório médico"
    assert requisitos.rotulo(r, "desconhecido_x") == "desconhecido x"
