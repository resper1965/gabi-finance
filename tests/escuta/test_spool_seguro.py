import os

import pytest

from gabi.escuta import spool_seguro as ss


@pytest.fixture
def spool(tmp_path):
    p = tmp_path / "spool"
    (p / "anexos").mkdir(parents=True)
    return p


def _arq(spool, nome="a.pdf", dados=b"%PDF-real"):
    a = spool / "anexos" / nome
    a.write_bytes(dados)
    return a


def _troca_por_symlink(spool, vitima_dir):
    """O ouvinte comprometido troca `anexos` por um symlink para uma pasta do brain."""
    os.rename(spool / "anexos", spool / "anexos-original")
    (spool / "anexos").symlink_to(vitima_dir, target_is_directory=True)


def test_abrir_le_anexo_normal_e_devolve_nome(spool):
    a = _arq(spool)
    assert ss.abrir_anexo(spool, str(a)) == (b"%PDF-real", "a.pdf")


def test_apagar_remove_anexo_dentro_do_anexos(spool):
    a = _arq(spool)
    assert ss.apagar_anexo(spool, str(a)) is True
    assert not a.exists()
    assert ss.apagar_anexo(spool, str(a)) is False  # já não existe


@pytest.mark.parametrize("fazer", [
    lambda s: s / "a.pdf",                      # direto no spool, fora de anexos/
    lambda s: s / "anexos" / "sub" / "a.pdf",   # componente extra
    lambda s: s / "anexos" / ".." / "a.pdf",
    lambda s: s / "anexos" / "..",
    lambda s: s / "anexos" / ".",
    lambda s: s.parent / "fora" / "anexos" / "a.pdf",
    lambda s: "relativo/a.pdf",
    lambda s: "",
])
def test_caminho_que_nao_e_exatamente_spool_anexos_nome_e_recusado(spool, fazer):
    (spool / "sub").mkdir(exist_ok=True)
    for f in (spool / "a.pdf", spool / "anexos" / "sub" / "a.pdf"):
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
    caminho = str(fazer(spool))
    with pytest.raises((RuntimeError, ValueError, OSError)):
        ss.abrir_anexo(spool, caminho)
    assert ss.apagar_anexo(spool, caminho) is False
    assert (spool / "a.pdf").exists() and (spool / "anexos" / "sub" / "a.pdf").exists()


def test_anexos_symlink_desde_o_inicio_nao_le_nem_apaga(spool, tmp_path):
    vitima = tmp_path / "dados-do-brain"
    vitima.mkdir()
    (vitima / "a.pdf").write_bytes(b"SEGREDO")
    _troca_por_symlink(spool, vitima)
    caminho = str(spool / "anexos" / "a.pdf")
    with pytest.raises((RuntimeError, OSError)):
        ss.abrir_anexo(spool, caminho)
    assert ss.apagar_anexo(spool, caminho) is False
    assert (vitima / "a.pdf").read_bytes() == b"SEGREDO"


def test_troca_de_anexos_entre_a_validacao_e_o_uso_nao_apaga_a_vitima(spool, tmp_path, monkeypatch):
    vitima = tmp_path / "dados-do-brain"
    vitima.mkdir()
    (vitima / "a.pdf").write_bytes(b"SEGREDO")
    a = _arq(spool)
    monkeypatch.setattr(ss, "_gancho", lambda: _troca_por_symlink(spool, vitima))
    assert ss.apagar_anexo(spool, str(a)) is True
    assert (vitima / "a.pdf").read_bytes() == b"SEGREDO"          # a vítima nunca foi tocada
    assert not (spool / "anexos-original" / "a.pdf").exists()      # apagou o do diretório original (descritor)


def test_troca_de_anexos_entre_a_validacao_e_a_leitura_nao_le_a_vitima(spool, tmp_path, monkeypatch):
    vitima = tmp_path / "dados-do-brain"
    vitima.mkdir()
    (vitima / "a.pdf").write_bytes(b"SEGREDO")
    a = _arq(spool)
    monkeypatch.setattr(ss, "_gancho", lambda: _troca_por_symlink(spool, vitima))
    assert ss.abrir_anexo(spool, str(a)) == (b"%PDF-real", "a.pdf")


def test_arquivo_symlink_fifo_e_teto(spool, tmp_path):
    import signal
    fora = tmp_path / "fora.txt"
    fora.write_bytes(b"SEGREDO")
    (spool / "anexos" / "ln.pdf").symlink_to(fora)
    os.mkfifo(spool / "anexos" / "fifo.pdf")
    _arq(spool, "grande.pdf", b"x" * 100)
    signal.alarm(5)
    try:
        for nome in ("ln.pdf", "fifo.pdf"):
            with pytest.raises((RuntimeError, OSError)):
                ss.abrir_anexo(spool, str(spool / "anexos" / nome))
        with pytest.raises(RuntimeError):
            ss.abrir_anexo(spool, str(spool / "anexos" / "grande.pdf"), max_bytes=10)
    finally:
        signal.alarm(0)
    assert fora.read_bytes() == b"SEGREDO"
