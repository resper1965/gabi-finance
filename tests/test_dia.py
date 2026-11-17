"""Bloco dinheiro do dia (o que sobrou de gabi/dia.py no corte): saldo, atrasadas, o que sai hoje e o pago hoje. Só lê tabelas prontas."""
import inspect

from gabi import dia
from gabi.db import conectar

from tests.rotas.test_dinheiro_api import AGORA, banco  # noqa: F401  (fixture)


def test_hoje_traz_so_o_bloco_dinheiro(banco):
    d = dia.hoje(conectar(banco), AGORA)
    assert set(d) == {"dinheiro"}
    assert d["dinheiro"]["atrasadas"]["n"] == 1  # a mesma asserção financeira que o teste da rota /hoje fazia


def test_hoje_le_so_de_tabelas_prontas():
    fonte = inspect.getsource(dia)
    assert "fontes." not in fonte and "urllib" not in fonte and "httpx" not in fonte
