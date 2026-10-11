import re

import pytest

from gabi.fontes.paperless import ErroPaperless, Paperless
from tests.cobrar.paperless_falso import PaperlessFalso


def _cli(**kw):
    srv = PaperlessFalso(**kw)
    return Paperless("http://p", "tok-gabi", http=srv), srv


def test_paperless_enviar_so_etiquetas_permitidas():
    cli, srv = _cli()
    for ruim in (["pago"], ["gabi:ok", "outra"], []):
        with pytest.raises(ValueError):
            cli.enviar(b"x", "a.pdf", ruim)
    assert srv.enviados == [] and srv.chamadas == []


def test_enviar_monta_multipart_com_arquivo_e_etiqueta():
    cli, srv = _cli()
    r = cli.enviar(b"%PDF-conteudo", "exame.pdf", ["gabi:saude-exame"])
    assert r == "tarefa-uuid-1"
    corpo, cab = srv.enviados[0]
    assert cab["Authorization"] == "Token tok-gabi"
    fronteira = re.search(r"boundary=(\S+)", cab["Content-Type"]).group(1)
    assert cab["Content-Type"].startswith("multipart/form-data")
    assert b'name="document"; filename="exame.pdf"' in corpo and b"%PDF-conteudo" in corpo
    assert corpo.endswith(f"--{fronteira}--\r\n".encode())
    assert f'name="tags"\r\n\r\n{srv.tags["gabi:saude-exame"]}\r\n'.encode() in corpo


def test_enviar_nome_nao_injeta_cabecalho_nem_caminho():
    cli, srv = _cli()
    cli.enviar(b"x", '../../x"\r\nEvil: 1.pdf', ["gabi:entrada-whatsapp"])
    corpo = srv.enviados[0][0]
    linha = corpo.split(b'name="document"; ')[1].split(b"\r\n")[0]  # a linha filename= inteira
    assert linha.startswith(b'filename="') and linha.endswith(b'"') and b'"' not in linha[len(b'filename="'):-1]
    assert b"\r" not in linha and b"\n" not in linha and b"/" not in linha
    assert b"\r\nEvil:" not in corpo


def test_enviar_erro_nao_vaza_token_nem_conteudo():
    def http(metodo, url, corpo=None, cab=None):
        if "post_document" in url:
            return 500, {"detail": "token tok-secreto CONTEUDO-SECRETO"}  # corpo do erro com segredos: nunca entra na exceção
        return PaperlessFalso()(metodo, url, corpo, cab)

    cli = Paperless("http://p", "tok-secreto", http=http)
    with pytest.raises(ErroPaperless) as e:
        cli.enviar(b"CONTEUDO-SECRETO", "a.pdf", ["gabi:x"])
    assert "tok-secreto" not in str(e.value) and "CONTEUDO-SECRETO" not in str(e.value) and "500" in str(e.value)
