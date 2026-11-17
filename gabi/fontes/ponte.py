"""Ponte Unix entre a API/MCP (sem rede) e o serviço de fontes (com rede, dono do token do Nibo).
Uma requisição por conexão: JSON de uma linha {"fonte", "metodo", "args", "kwargs"} -> {"ok": valor} | {"erro": {"tipo", "msg"}}.
`bytes` viaja como {"__b64__": ...}. Só métodos da lista branca; `preparar_usuario` (token admin) nunca atravessa a ponte.
R5: nenhum token ou cabeçalho trafega aqui; o servidor devolve só o tipo e a mensagem do erro. Consome: fontes.nibo."""
import base64
import datetime as dt
import json
import os
import socket
import socketserver
from pathlib import Path

from gabi.fontes.nibo import ErroNibo

MAX_BYTES = 64 * 1024 * 1024
ESPERA_PEDIDO = 30  # segundos para o pedido chegar inteiro; cliente mudo é desconectado
PERMITIDOS = {
    "nibo": frozenset({"nfse", "agendamentos_a_receber", "obter_arquivo"}),  # ADR-023: só o que notas_importar lê; o lote (escrita) saiu
}
ERROS = {"nibo": ErroNibo}


def _codificar(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()  # o outro lado (métodos do Nibo) aceita o texto ISO
    if isinstance(v, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, dict):
        return {k: _codificar(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_codificar(x) for x in v]
    return v


def _decodificar(v):
    if isinstance(v, dict):
        if set(v) == {"__b64__"}:
            return base64.b64decode(v["__b64__"])
        return {k: _decodificar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decodificar(x) for x in v]
    return v


def _ler_tudo(c) -> bytes:
    partes, total = [], 0
    while True:
        p = c.recv(1 << 20)
        if not p:
            return b"".join(partes)
        total += len(p)
        if total > MAX_BYTES:
            raise ValueError("requisição grande demais")
        partes.append(p)


def _atender(fontes: dict, bruto: bytes) -> dict:
    """fontes: {"nibo": objeto|None}. Nunca levanta: erro vira {"erro": ...}."""
    try:
        req = json.loads(bruto)
        fonte, metodo = req["fonte"], req["metodo"]
        if metodo == "estado":
            return {"ok": {n: o is not None for n, o in fontes.items()}}
        if fonte not in PERMITIDOS or metodo not in PERMITIDOS[fonte]:
            return {"erro": {"tipo": "metodo_proibido", "msg": f"{fonte}.{metodo} não é permitido"}}
        objeto = fontes.get(fonte)
        if objeto is None:
            return {"erro": {"tipo": "nao_configurada", "msg": f"{fonte} não está configurado no serviço de fontes"}}
        r = getattr(objeto, metodo)(*_decodificar(req.get("args", [])), **_decodificar(req.get("kwargs", {})))
        if hasattr(r, "__next__"):
            r = list(r)
        return {"ok": _codificar(r)}
    except tuple(ERROS.values()) as e:
        tipo = next(c.__name__ for c in ERROS.values() if isinstance(e, c))  # subclasses (TagInvalida) cruzam como a base
        return {"erro": {"tipo": tipo, "msg": str(e)}}
    except Exception as e:  # nunca vaza traço (pode conter URL/cabeçalho)
        return {"erro": {"tipo": "interno", "msg": type(e).__name__}}


class Servidor(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, caminho, fontes: dict):
        self.fontes = fontes
        Path(caminho).unlink(missing_ok=True)
        super().__init__(str(caminho), _Manipulador)
        os.chmod(caminho, 0o660)


class _Manipulador(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(ESPERA_PEDIDO)
        try:
            bruto = _ler_tudo(self.request)
        except TimeoutError:  # cliente mudo: fecha sem responder
            return
        except ValueError as e:
            resp = {"erro": {"tipo": "interno", "msg": str(e)}}
        else:
            self.request.settimeout(None)
            resp = _atender(self.server.fontes, bruto)
        self.request.sendall(json.dumps(resp).encode())


class Ponte:
    """Cliente: objeto com os mesmos métodos do NiboEscrita, mas executados no serviço de fontes."""

    def __init__(self, caminho, fonte: str):
        self._caminho, self._fonte = str(caminho), fonte

    def _chamar(self, metodo, args=(), kwargs=None):
        erro = ERROS[self._fonte]
        corpo = json.dumps({"fonte": self._fonte, "metodo": metodo, "args": _codificar(list(args)), "kwargs": _codificar(kwargs or {})}).encode()
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(130)
                s.connect(self._caminho)
                s.sendall(corpo)
                s.shutdown(socket.SHUT_WR)
                resp = json.loads(_ler_tudo(s))
        except (OSError, ValueError):
            raise erro("serviço de fontes indisponível") from None
        if "erro" in resp:
            t, msg = resp["erro"]["tipo"], resp["erro"]["msg"]
            raise erro(msg if t in (erro.__name__, "nao_configurada") else f"{t}: {msg}")
        return _decodificar(resp["ok"])

    def configurada(self) -> bool:
        try:
            return bool(self._chamar("estado").get(self._fonte))
        except tuple(ERROS.values()):
            return False

    def __getattr__(self, nome):
        if nome.startswith("_") or nome not in PERMITIDOS[self._fonte]:
            raise AttributeError(nome)
        return lambda *a, **k: self._chamar(nome, a, k)
