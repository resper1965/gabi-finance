import pytest

from gabi.dinheiro.valor import formatar, para_centavos, somar


@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,56", 123456), ("1234.56", 123456), ("1234,56", 123456), ("BRL312.45", 31245), ("R$ 1.000,00", 100000),
    ("R$ -10,00", -1000), ("-1.234,56", -123456), ("1.234.567", 123456700), ("0,1", 10), ("  7  ", 700),
    (312.45, 31245), (7, 700), (-0.05, -5), ("0", 0),
])
def test_para_centavos_formatos(entrada, esperado):
    assert para_centavos(entrada) == esperado


@pytest.mark.parametrize("vazio", [None, "", "   "])
def test_vazio_vira_none(vazio):
    assert para_centavos(vazio) is None


@pytest.mark.parametrize("ruim", ["abc", "12,3,4", "R$", "1.2.3,4,5", "--5"])
def test_valor_invalido_levanta_ValueError(ruim):
    with pytest.raises(ValueError):
        para_centavos(ruim)


def test_valor_float_nao_acumula_erro():
    assert somar(*[para_centavos(0.1)] * 10) == 100  # 10 x 0,10 = 1,00 exato (float daria 0.9999999999999999)


def test_arredonda_meio_para_cima_em_centavos():
    assert para_centavos("0,005") == 1 and para_centavos("0,004") == 0 and para_centavos("2.675") == 268


def test_formatar_positivo_negativo_e_zero():
    assert formatar(123456) == "1234.56" and formatar(-5) == "-0.05" and formatar(0) == "0.00" and formatar(100) == "1.00"


def test_formatar_e_para_centavos_sao_inversos():
    for c in (0, 1, 99, 100, 123456, -123456, 10**12):
        assert para_centavos(formatar(c)) == c


def test_somar_vazio_e_com_negativos():
    assert somar() == 0 and somar(500, -200, -300) == 0
