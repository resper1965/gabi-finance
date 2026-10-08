import pytest

from gabi.mascara import mascarar_documento, mascarar_texto


@pytest.mark.parametrize("entrada,saida", [
    ("123.456.789-09", "***.***.***-09"),
    ("98765432100", "*********00"),
    ("12345-6", "****5-6"),
])
def test_mascarar_documento_mantem_dois_ultimos_digitos(entrada, saida):
    assert mascarar_documento(entrada) == saida


def test_mascara_cpf_dentro_de_texto_livre():
    t = "Pensão (CPF 111.222.333-44 do beneficiário) e outro 52998224725"
    r = mascarar_texto(t)
    assert "111.222.333-44" not in r and "52998224725" not in r
    assert "***.***.***-44" in r and "*********25" in r
    assert "Pensão" in r and "beneficiário" in r


def test_mascara_nao_toca_valores_monetarios_nem_datas():
    assert mascarar_texto("R$ 1.000,00 em 2030-12-31 dia 5") == "R$ 1.000,00 em 2030-12-31 dia 5"


def test_telefone_com_ddi_nao_e_mascarado():
    assert mascarar_texto("+5511900000001") == "+5511900000001"
    assert mascarar_texto("+55 11 90000-0001") == "+55 11 90000-0001"


@pytest.mark.parametrize("texto", [
    "111.222.333-44,555.666.777-88", "CPF-12345678909", "CPF.12345678909", "CPF n.12345678909",
    "CPF/12345678909", "123 456 789 09", "123.456.789 09", "123456789-09", "123.456.789.09",
    "123.456.789/09", "123.456.789\u201309", "123.456.789-09/2020",
])
def test_cpf_em_formatos_variados_e_mascarado(texto):
    r = mascarar_texto(texto)
    digitos_visiveis = [c for c in r if c.isdigit()]
    assert "123" not in r.replace("2020", "") and "111.222" not in r and "555.666" not in r
    assert len(digitos_visiveis) <= 4 + (4 if "2020" in texto else 0)


@pytest.mark.parametrize("texto", ["11987654321", "+55 11987654321", "R$ 12345678901", "12.345.678/0001-90"])
def test_nao_mascara_telefone_valor_nem_cnpj(texto):
    assert mascarar_texto(texto) == texto


def test_cpf_com_digito_verificador_valido_sem_pontuacao_e_mascarado():
    assert mascarar_texto("52998224725") == "*********25"
