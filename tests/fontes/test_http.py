import pathlib
import urllib.request

from gabi.fontes._http import SemCredencialEntreHosts

FONTES = pathlib.Path(__file__).resolve().parents[2] / "gabi" / "fontes"
CABECALHOS = {"Authorization": "Bearer s", "ApiToken": "t", "X-Api-Key": "k", "X-Auth-Foo": "f", "Accept": "x"}


def _novo(destino):
    req = urllib.request.Request("https://a.example/", headers=CABECALHOS)
    req.add_unredirected_header("Authorization", "Bearer u")
    return SemCredencialEntreHosts().redirect_request(req, None, 302, "Found", {}, destino)


def test_redirecionamento_outro_host_tira_credencial():
    novo = _novo("https://outro.example/x")
    nomes = {n.lower() for n in novo.headers} | {n.lower() for n in novo.unredirected_hdrs}
    assert not nomes & {"authorization", "apitoken", "x-api-key", "x-auth-foo"}
    assert novo.get_header("Accept") == "x"


def test_redirecionamento_mesmo_host_mantem():
    novo = _novo("https://a.example/y")
    assert novo.get_header("Authorization") == "Bearer s" and novo.get_header("Apitoken") == "t"


def test_redirecionamento_https_para_http_tira_credencial():
    novo = _novo("http://a.example/y")
    nomes = {n.lower() for n in novo.headers} | {n.lower() for n in novo.unredirected_hdrs}
    assert not nomes & {"authorization", "apitoken", "x-api-key", "x-auth-foo"}


def test_clientes_nao_usam_urlopen_direto():
    maus = [f.name for f in FONTES.glob("*.py") if f.name != "graph_ness.py" and "urllib.request.urlopen(" in f.read_text()]
    assert maus == []


def _fila(*status):
    fila = list(status)
    chamadas = []

    def fazer():
        chamadas.append(1)
        return fila.pop(0), {}
    return fazer, chamadas


def test_com_retry_repete_429_e_para_no_ok():
    from gabi.fontes._http import com_retry
    fazer, chamadas = _fila(429, 503, 200)
    esperas = []
    assert com_retry(fazer, dorme=esperas.append)[0] == 200
    assert esperas == [2, 5] and len(chamadas) == 3


def test_com_retry_desiste_depois_de_duas():
    from gabi.fontes._http import com_retry
    fazer, chamadas = _fila(503, 503, 503)
    assert com_retry(fazer, dorme=lambda s: None)[0] == 503
    assert len(chamadas) == 3


def test_com_retry_nao_repete_404():
    from gabi.fontes._http import com_retry
    fazer, chamadas = _fila(404)
    assert com_retry(fazer, dorme=lambda s: None)[0] == 404
    assert len(chamadas) == 1
