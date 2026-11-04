"""HTTP mínimo compartilhado pelos clientes novos: (metodo, url, corpo, cabecalhos) -> (status, json). Nunca registra cabeçalhos (R5)."""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


_CABECALHOS_CREDENCIAL = ("authorization", "apitoken", "x-api-key")


class SemCredencialEntreHosts(urllib.request.HTTPRedirectHandler):
    """Redirecionamento para outro host não leva a credencial (o urllib copiaria os cabeçalhos)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        novo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if novo is not None and urlsplit(novo.full_url)[:2] != urlsplit(req.full_url)[:2]:  # (esquema, host): https->http também tira
            for dic in (novo.headers, novo.unredirected_hdrs):
                for nome in [n for n in dic if n.lower() in _CABECALHOS_CREDENCIAL or n.lower().startswith("x-auth")]:
                    del dic[nome]
        return novo


abrir = urllib.request.build_opener(SemCredencialEntreHosts).open


def http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with abrir(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, {"error": {"message": e.reason}}
    except OSError as e:
        raise ConnectionError(f"fonte indisponível: {type(e).__name__}") from None


REPETIR = {429, 502, 503, 504}
dormir = time.sleep  # os testes trocam por um no-op (conftest); com_retry lê daqui na hora da chamada


def com_retry(fazer, *, dorme=None, esperas=(2, 5)):
    """Só para LEITURA: repete `fazer()` (-> (status, resp)) enquanto o status ∈ REPETIR, esperando 2 s e depois 5 s; devolve o último resultado.
    Escrita não passa por aqui (repetir um POST pode duplicar o efeito)."""
    dorme = dorme or dormir
    status, resp = fazer()
    for espera in esperas:
        if status not in REPETIR:
            break
        dorme(espera)
        status, resp = fazer()
    return status, resp
