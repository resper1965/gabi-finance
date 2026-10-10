import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.crise import palavras_risco, tem_risco

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def test_tem_risco_sem_acento_e_caixa():
    assert tem_risco("Não aguento MAIS, quero me MATAR", ["matar"])
    assert tem_risco("preciso de ajuda urgente", ["URGÊNCIA", "Ajuda"])
    assert not tem_risco("tudo bem", ["matar"])


def test_palavra_inteira_nao_casa_pedaco():
    assert not tem_risco("vou tomar um amatar", ["matar"])
    assert not tem_risco("socorrista chegou", ["socorro"])
    assert tem_risco("socorro!", ["socorro"])


def test_multi_palavra():
    assert tem_risco("eu vou  me matar hoje", ["me matar"])
    assert not tem_risco("eu vou me matarei", ["me matar"])


def test_lista_sem_entradas_vazias():
    assert not tem_risco("qualquer coisa", ["", "  "])


def test_sem_parametro_lista_vazia(con):
    assert palavras_risco(con) == []


def test_parametro_lido_do_banco(con):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (json.dumps(["socorro", "me matar"]),))
    assert palavras_risco(con) == ["socorro", "me matar"]


@pytest.mark.parametrize("valor", ["", "não é json", '{"a":1}', '"x"'])
def test_parametro_invalido_lista_vazia(con, valor):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (valor,))
    assert palavras_risco(con) == []


def test_parametro_ignora_itens_nao_texto(con):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (json.dumps(["socorro", 3, None]),))
    assert palavras_risco(con) == ["socorro"]
