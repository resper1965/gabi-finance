import pytest

from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.roteador import roteador_contatos

NESS, GMAIL = "resper@ness.com.br", "resper@gmail.com"


def _fonte(nome):
    chamadas = []

    def listar(conta):
        chamadas.append(conta)
        return [{"nome": nome, "telefone": "1"}]
    listar.chamadas = chamadas
    return listar


def test_roteia_por_conta_sem_diferenciar_caixa():
    google, graph = _fonte("g"), _fonte("m")
    r = roteador_contatos(google, graph, [NESS])
    assert r(NESS)[0]["nome"] == "m" and r("RESPER@Ness.com.br")[0]["nome"] == "m" and r(GMAIL)[0]["nome"] == "g"
    assert google.chamadas == [GMAIL] and len(graph.chamadas) == 2


def test_fonte_ausente_vira_nao_autorizada():
    with pytest.raises(ErroGoogleOAuth, match="^conta não autorizada: " + NESS):
        roteador_contatos(_fonte("g"), None, [NESS])(NESS)
    with pytest.raises(ErroGoogleOAuth, match="^conta não autorizada: " + GMAIL):
        roteador_contatos(None, _fonte("m"), [NESS])(GMAIL)


def test_contatos_pela_ponte_sem_nenhuma_fonte_e_none(tmp_path):
    import threading

    from gabi.fontes.ponte import Servidor
    from gabi.fontes.roteador import contatos_pela_ponte
    srv = Servidor(tmp_path / "v.sock", {"google_contatos": None, "graph_ness": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert contatos_pela_ponte(tmp_path / "v.sock") is None
    finally:
        srv.shutdown(); srv.server_close()


def test_contatos_pela_ponte_roteia_a_ness_ao_graph(tmp_path):
    import threading

    from gabi.fontes.ponte import Servidor
    from gabi.fontes.roteador import contatos_pela_ponte

    class G:
        def contas(self):
            return [NESS]

        def contatos(self, conta):
            return [{"nome": "m", "telefone": "1"}]

    srv = Servidor(tmp_path / "w.sock", {"google_contatos": None, "graph_ness": G()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        listar = contatos_pela_ponte(tmp_path / "w.sock")
        assert listar(NESS)[0]["nome"] == "m"
        with pytest.raises(ErroGoogleOAuth, match="^conta não autorizada"):
            listar(GMAIL)
    finally:
        srv.shutdown(); srv.server_close()
