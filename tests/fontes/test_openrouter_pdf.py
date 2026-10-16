"""`completar_pdf` do OpenRouter e da ponte: PDF em base64 pelo plugin de arquivos, tetos, recusa antes da rede, custo. Sem rede (http falso)."""
import base64
import threading

import pytest

from gabi.fontes.openrouter import ErroOpenRouter, Limites, OpenRouter
from gabi.fontes.ponte import PERMITIDOS, Ponte, PonteModelo, Servidor

CHAVE = "sk-or-SEGREDO123"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n2 0 obj << /Type /Pages >> endobj\n"


def _ok():
    chamadas = []

    def http(metodo, url, corpo=None, cab=None):
        chamadas.append(corpo)
        return 200, {"choices": [{"message": {"content": "{}"}}], "usage": {"cost": 0.004}}
    return http, chamadas


def test_envia_pdf_em_base64_pelo_plugin_de_arquivos_modelo_rapido():
    http, chamadas = _ok()
    o = OpenRouter(CHAVE, "rapido/m", "forte/m", http=http)
    assert o.completar_pdf(PDF, "leia") == ("{}", 0.004)
    c = chamadas[0]
    assert c["model"] == "rapido/m" and c["plugins"] == [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]
    texto, arq = c["messages"][0]["content"]
    assert texto == {"type": "text", "text": "leia"} and arq["type"] == "file"
    assert base64.b64decode(arq["file"]["file_data"].split(",", 1)[1]) == PDF
    o.completar_pdf(PDF, "leia", forte=True)
    assert chamadas[1]["model"] == "forte/m"


def test_recusas_antes_da_rede():
    http, chamadas = _ok()
    o = OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(max_pdf_bytes=300, max_pdf_paginas=2))
    for pdf, msg in ((b"nao e pdf", "pdf inválido"), (None, "pdf inválido"), (PDF + b"x" * 300, "pdf grande demais"),
                     (PDF * 3, "pdf com páginas demais")):
        with pytest.raises(ErroOpenRouter, match=msg):
            o.completar_pdf(pdf, "p")
    assert chamadas == []
    with pytest.raises(ErroOpenRouter, match="chave ausente"):
        OpenRouter("", "a", "b", http=http).completar_pdf(PDF, "p")


def test_chamada_so_pode_baixar_os_tetos_do_servico():
    http, chamadas = _ok()
    o = OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(max_pdf_bytes=1000))
    with pytest.raises(ErroOpenRouter, match="pdf grande demais"):
        o.completar_pdf(PDF, "p", max_bytes=10)
    assert o.completar_pdf(PDF, "p", max_bytes=10**9)  # pedir mais que o serviço não adianta, mas este PDF cabe
    with pytest.raises(ErroOpenRouter, match="pdf grande demais"):
        OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(max_pdf_bytes=10)).completar_pdf(PDF, "p", max_bytes=10**9)


def test_teto_diario_recusa_sem_enviar_e_reserva_inclui_paginas():
    http, chamadas = _ok()
    o = OpenRouter(CHAVE, "a", "b", http=http, limites=Limites(teto_dia_usd=0.04))
    with pytest.raises(ErroOpenRouter, match="teto diário"):
        o.completar_pdf(PDF, "p")  # a reserva do PDF (página + OCR) passa do teto
    assert chamadas == []


def test_falha_depois_do_envio_mantem_reserva_e_nao_vaza_a_chave():
    def http(*a, **k):
        raise OSError(CHAVE)
    o = OpenRouter(CHAVE, "a", "b", http=http)
    with pytest.raises(ErroOpenRouter) as e:
        o.completar_pdf(PDF, "p")
    assert CHAVE not in str(e.value) and o._gasto > 0


def test_limites_pdf_do_ambiente():
    assert Limites().max_pdf_bytes == 8 * 1024 * 1024 and Limites().max_pdf_paginas == 10
    l = Limites.do_ambiente({"OPENROUTER_MAX_PDF_BYTES": "5", "OPENROUTER_MAX_PDF_PAGINAS": "lixo"})
    assert (l.max_pdf_bytes, l.max_pdf_paginas) == (5, 10)


def test_ponte_leva_o_pdf_e_devolve_texto_e_custo(tmp_path):
    http, chamadas = _ok()
    sock = tmp_path / "s.sock"
    srv = Servidor(sock, {"openrouter": OpenRouter(CHAVE, "a", "b", http=http)})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert "completar_pdf" in PERMITIDOS["openrouter"]
        assert PonteModelo(sock).completar_pdf(PDF, "leia") == ("{}", 0.004)
        assert base64.b64decode(chamadas[0]["messages"][0]["content"][1]["file"]["file_data"].split(",", 1)[1]) == PDF
        with pytest.raises(ErroOpenRouter, match="pdf grande demais"):
            PonteModelo(sock).completar_pdf(PDF, "leia", max_bytes=5)
        assert len(chamadas) == 1
    finally:
        srv.shutdown()
        srv.server_close()
