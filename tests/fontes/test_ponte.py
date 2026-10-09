import threading

import pytest

from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.paperless import ErroPaperless
from gabi.fontes.ponte import Ponte, Servidor


class PaperlessFalso:
    def docs(self, **f):
        return [{"id": 1, "title": "x", **f}]

    def baixar(self, id):
        return b"%PDF\x00\xff" + bytes([id])

    def preparar_usuario(self, token_admin):
        return "segredo"

    def etiquetar(self, id, tags):
        raise ErroPaperless("PATCH /x -> 500")


class NiboFalso:
    def __init__(self):
        self.anexos = []

    def anexar_arquivo(self, sid, nome, conteudo):
        self.anexos.append((sid, nome, conteudo))

    def socios(self):
        return iter([{"id": "s1"}])

    def agendamento_por_reference(self, reference):
        return None

    def explode(self):
        raise RuntimeError("token=abc")


@pytest.fixture
def ponte(tmp_path):
    nibo = NiboFalso()
    srv = Servidor(tmp_path / "f.sock", {"paperless": PaperlessFalso(), "nibo": nibo})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield tmp_path / "f.sock", nibo
    srv.shutdown()
    srv.server_close()


def test_chamada_simples_e_bytes_ida_e_volta(ponte):
    sock, nibo = ponte
    p, n = Ponte(sock, "paperless"), Ponte(sock, "nibo")
    assert p.docs(query="luz") == [{"id": 1, "title": "x", "query": "luz"}]
    assert p.baixar(7) == b"%PDF\x00\xff\x07"
    n.anexar_arquivo("s", "a.pdf", b"\x00\x01bin")
    assert nibo.anexos == [("s", "a.pdf", b"\x00\x01bin")]
    assert n.agendamento_por_reference("r") is None


def test_gerador_vira_lista(ponte):
    assert Ponte(ponte[0], "nibo").socios() == [{"id": "s1"}]


def test_erro_da_fonte_volta_como_a_mesma_excecao(ponte):
    with pytest.raises(ErroPaperless, match="PATCH /x -> 500"):
        Ponte(ponte[0], "paperless").etiquetar(1, ["a"])


def test_metodo_fora_da_lista_branca_nao_existe_e_nem_o_servidor_aceita(ponte):
    p = Ponte(ponte[0], "paperless")
    with pytest.raises(AttributeError):
        p.preparar_usuario("tok")
    with pytest.raises(ErroPaperless, match="metodo_proibido"):
        p._chamar("preparar_usuario", ("tok",))


def test_excecao_inesperada_nao_vaza_mensagem(ponte):
    with pytest.raises(ErroNibo) as e:
        Ponte(ponte[0], "nibo")._chamar("criar_agendamento_debito", (), {"x": 1})  # o falso não tem esse método: AttributeError no servidor
    assert "token" not in str(e.value) and "abc" not in str(e.value)


def test_fonte_nao_configurada(tmp_path):
    srv = Servidor(tmp_path / "g.sock", {"paperless": None, "nibo": PaperlessFalso()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert Ponte(tmp_path / "g.sock", "paperless").configurada() is False
        assert Ponte(tmp_path / "g.sock", "nibo").configurada() is True
        with pytest.raises(ErroPaperless, match="não está configurado"):
            Ponte(tmp_path / "g.sock", "paperless").docs()
    finally:
        srv.shutdown()
        srv.server_close()


def test_servico_fora_do_ar_vira_erro_da_fonte(tmp_path):
    with pytest.raises(ErroNibo, match="indisponível"):
        Ponte(tmp_path / "nada.sock", "nibo").socios()
    assert Ponte(tmp_path / "nada.sock", "nibo").configurada() is False


def test_ambiente_com_socket_usa_a_ponte_e_devolve_none_se_nao_configurada(tmp_path, monkeypatch):
    srv = Servidor(tmp_path / "h.sock", {"paperless": PaperlessFalso(), "nibo": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "h.sock"))
        f = fontes_do_ambiente()
        assert f["nibo"]() is None
        assert f["paperless"]().baixar(2) == b"%PDF\x00\xff\x02"
    finally:
        srv.shutdown()
        srv.server_close()


def test_socket_so_para_dono_e_grupo(ponte):
    import stat
    assert stat.S_IMODE(ponte[0].stat().st_mode) == 0o660
