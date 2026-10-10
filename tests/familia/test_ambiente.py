import base64

import pytest

from gabi.familia.ambiente import saude_do_ambiente

K = bytes(range(32))


def test_sem_arquivo_de_chave_devolve_none(tmp_path):
    assert saude_do_ambiente(tmp_path, {}) is None
    assert saude_do_ambiente(tmp_path, {"GABI_SAUDE_CHAVE_ARQUIVO": str(tmp_path / "nao-existe")}) is None


@pytest.mark.parametrize("conteudo", [K, K.hex().encode() + b"\n", base64.b64encode(K) + b"\n"])
def test_aceita_chave_crua_hex_ou_base64(tmp_path, conteudo):
    (tmp_path / "k").write_bytes(conteudo)
    arq, chave = saude_do_ambiente(tmp_path, {"GABI_SAUDE_CHAVE_ARQUIVO": str(tmp_path / "k")})
    assert chave == K and arq == tmp_path / "saude.enc"


def test_chave_de_tamanho_errado_levanta(tmp_path):
    (tmp_path / "k").write_bytes(b"curta")
    with pytest.raises(ValueError):
        saude_do_ambiente(tmp_path, {"GABI_SAUDE_CHAVE_ARQUIVO": str(tmp_path / "k")})
