"""Cópias privadas de `correio.regras.endereco` e `contatos.telefone.normalizar_telefone` (o correio e os contatos saíram do gabi-finance)."""
import pytest

from gabi import decisoes


@pytest.mark.parametrize("texto,esperado", [
    ("ana@x.com", "ana@x.com"), ("Ana Silva <ANA.Silva@Empresa.COM>", "ana.silva@empresa.com"), ('"Silva, Ana" <ana@x.com>', "ana@x.com"),
    ("sem endereco", None), ("", None), (None, None), (3, None), ("a@b", None), ("a b@x.com", None)])
def test_endereco_extrai_de_nome_e_angulos(texto, esperado):
    assert decisoes._endereco(texto) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("+55 11 91234-5678", "+5511912345678"), ("(11) 91234-5678", "+5511912345678"), ("11 1234-5678", "+551112345678"),
    ("1187654321", "+5511987654321"),  # celular antigo (8 dígitos começando em 6-9) ganha o 9
    ("5511912345678@s.whatsapp.net", "+5511912345678"), ("5511912345678@c.us", "+5511912345678"),
    ("123@lid", None), ("5511912345678@g.us", None), ("123", None), ("", None), (None, None)])
def test_normalizar_telefone_e164_brasileiro(bruto, esperado):
    assert decisoes._normalizar_telefone(bruto) == esperado
