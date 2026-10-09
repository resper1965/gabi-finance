"""HTTP mínimo compartilhado pelos clientes novos: (metodo, url, corpo, cabecalhos) -> (status, json). Nunca registra cabeçalhos (R5)."""
import json
import urllib.error
import urllib.request


def http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, {"error": {"message": e.reason}}
    except OSError as e:
        raise ConnectionError(f"fonte indisponível: {type(e).__name__}") from None
