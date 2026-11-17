import socket
import threading

import pytest

from gabi.fontes import ponte as mod_ponte
from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.ponte import ERROS, PERMITIDOS, Ponte, Servidor


class NiboFalso:
    def __init__(self):
        self.anexos = []

    def obter_arquivo(self, file_id):
        if file_id == "falha":
            raise ErroNibo("GET /x -> 500")
        return b"\x00\x01bin" + file_id.encode()

    def agendamentos_a_receber(self):
        return iter([{"scheduleId": "s1"}])

    def nfse(self, desde=None):
        return []

    def preparar_usuario(self, token_admin):
        return "segredo"

    def explode(self):
        raise RuntimeError("token=abc")


@pytest.fixture
def ponte(tmp_path):
    nibo = NiboFalso()
    srv = Servidor(tmp_path / "f.sock", {"nibo": nibo})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield tmp_path / "f.sock", nibo
    srv.shutdown()
    srv.server_close()


def test_chamada_simples_e_bytes_ida_e_volta(ponte):
    sock, nibo = ponte
    n = Ponte(sock, "nibo")
    assert n.obter_arquivo("f") == b"\x00\x01binf"
    assert n.nfse() == []


def test_gerador_vira_lista(ponte):
    assert Ponte(ponte[0], "nibo").agendamentos_a_receber() == [{"scheduleId": "s1"}]


def test_erro_da_fonte_volta_como_a_mesma_excecao(ponte):
    with pytest.raises(ErroNibo, match="GET /x -> 500"):
        Ponte(ponte[0], "nibo").obter_arquivo("falha")


def test_metodo_fora_da_lista_branca_nao_existe_e_nem_o_servidor_aceita(ponte):
    p = Ponte(ponte[0], "nibo")
    with pytest.raises(AttributeError):
        p.preparar_usuario("tok")
    with pytest.raises(ErroNibo, match="metodo_proibido"):
        p._chamar("preparar_usuario", ("tok",))


def test_excecao_inesperada_nao_vaza_mensagem(ponte):
    with pytest.raises(ErroNibo) as e:
        Ponte(ponte[0], "nibo")._chamar("criar_agendamento_debito", (), {"x": 1})  # o falso não tem esse método: AttributeError no servidor
    assert "token" not in str(e.value) and "abc" not in str(e.value)


def test_fonte_nao_configurada(tmp_path):
    srv = Servidor(tmp_path / "g.sock", {"nibo": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert Ponte(tmp_path / "g.sock", "nibo").configurada() is False
        with pytest.raises(ErroNibo, match="não está configurado"):
            Ponte(tmp_path / "g.sock", "nibo").nfse()
    finally:
        srv.shutdown()
        srv.server_close()


def test_servico_fora_do_ar_vira_erro_da_fonte(tmp_path):
    with pytest.raises(ErroNibo, match="indisponível"):
        Ponte(tmp_path / "nada.sock", "nibo").agendamentos_a_receber()
    assert Ponte(tmp_path / "nada.sock", "nibo").configurada() is False


def test_ambiente_com_socket_usa_a_ponte_e_devolve_none_se_nao_configurada(tmp_path, monkeypatch):
    srv = Servidor(tmp_path / "h.sock", {"nibo": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "h.sock"))
        f = fontes_do_ambiente()
        assert set(f) == {"nibo"}
        assert f["nibo"]() is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_socket_so_para_dono_e_grupo(ponte):
    import stat
    assert stat.S_IMODE(ponte[0].stat().st_mode) == 0o660

def test_ambiente_com_socket_e_sem_socket_so_tem_as_fontes_financeiras(tmp_path, monkeypatch):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert set(fontes_do_ambiente()) == {"nibo"}
    monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "x.sock"))
    assert set(fontes_do_ambiente()) == {"nibo"}


@pytest.mark.parametrize("fonte", ["google_email", "google_agenda", "google_contatos", "graph_ness", "openrouter", "paperless"])
def test_fonte_que_saiu_e_recusada_como_fonte_desconhecida(ponte, fonte):
    assert fonte not in PERMITIDOS and fonte not in ERROS
    with pytest.raises(KeyError):
        Ponte(ponte[0], fonte)._chamar("listar")  # nenhum erro tipado de fonte para ela
    # o servidor, por sua vez, recusa com o mesmo erro de método proibido que já usa
    resposta = mod_ponte._atender({"nibo": None}, ('{"fonte": "%s", "metodo": "listar", "args": [], "kwargs": {}}' % fonte).encode())
    assert resposta["erro"]["tipo"] == "metodo_proibido"


def test_nibo_so_leitura_que_tem_uso():
    """ADR-023: lote do Nibo, comprovantes e reembolso saíram; a ponte não pode mais deixar ninguém escrever no Nibo (R2)."""
    assert PERMITIDOS == {"nibo": frozenset({"nfse", "agendamentos_a_receber", "obter_arquivo"})}


# ---- Task 8: a ponte não espera para sempre por um cliente mudo ----
def test_servidor_desiste_de_cliente_mudo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod_ponte, "ESPERA_PEDIDO", 0.2)
    sock = tmp_path / "m.sock"
    srv = Servidor(sock, {"nibo": NiboFalso()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with socket.socket(socket.AF_UNIX) as c:
            c.settimeout(2)  # se o servidor não fechar, o teste falha em vez de travar
            c.connect(str(sock))
            assert c.recv(1) == b""  # nada enviado nem fechado pelo cliente: o servidor fecha sem resposta
    finally:
        srv.shutdown()
        srv.server_close()
