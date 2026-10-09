"""Servidor Paperless falso (em memória) para testar o cliente sem rede. Registra toda chamada em `.chamadas`."""
import re
from urllib.parse import unquote


class PaperlessFalso:
    def __init__(self, docs=None, tags=None, campos=None):
        self.docs = {d["id"]: d for d in (docs or [])}
        self.tags = dict(tags or {})  # nome -> id
        self.campos = dict(campos or {})  # nome -> id
        self.usuarios = {}
        self.chamadas = []  # (metodo, caminho, corpo, token)
        self._prox = 100

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        token = (cabecalhos or {}).get("Authorization", "")
        caminho = re.sub(r"^https?://[^/]+", "", url)
        self.chamadas.append((metodo, caminho, corpo, token))
        rota, _, qs = caminho.partition("?")
        if metodo == "GET" and rota == "/api/documents/":
            itens = list(self.docs.values())
            pagina = int(re.search(r"page=(\d+)", qs).group(1)) if "page=" in qs else 1
            ps = int(re.search(r"page_size=(\d+)", qs).group(1)) if "page_size=" in qs else 100
            fatia = itens[(pagina - 1) * ps: pagina * ps]
            prox = f"http://p/api/documents/?page={pagina + 1}&page_size={ps}" if pagina * ps < len(itens) else None
            return 200, {"count": len(itens), "next": prox, "results": fatia}
        m = re.fullmatch(r"/api/documents/(\d+)/download/", rota)
        if metodo == "GET" and m:
            return 200, b"%PDF-falso-" + m.group(1).encode()
        m = re.fullmatch(r"/api/documents/(\d+)/", rota)
        if m and int(m.group(1)) in self.docs:
            d = self.docs[int(m.group(1))]
            if metodo == "GET":
                return 200, d
            if metodo == "PATCH":
                d.update(corpo)
                return 200, d
        if rota == "/api/tags/":
            if metodo == "GET":
                nome = unquote(re.search(r"name__iexact=([^&]+)", qs).group(1)) if "name__iexact" in qs else None
                res = [{"id": i, "name": n} for n, i in self.tags.items() if nome is None or n.lower() == nome.lower()]
                return 200, {"count": len(res), "next": None, "results": res}
            if metodo == "POST":
                self._prox += 1
                self.tags[corpo["name"]] = self._prox
                return 201, {"id": self._prox, "name": corpo["name"]}
        if rota == "/api/custom_fields/":
            if metodo == "GET":
                return 200, {"count": len(self.campos), "next": None, "results": [{"id": i, "name": n} for n, i in self.campos.items()]}
            if metodo == "POST":
                self._prox += 1
                self.campos[corpo["name"]] = self._prox
                return 201, {"id": self._prox, "name": corpo["name"]}
        if rota == "/api/users/" and metodo == "POST":
            self.usuarios[corpo["username"]] = corpo
            return 201, {"id": 7, "username": corpo["username"]}
        if rota == "/api/token/" and metodo == "POST":
            return 200, {"token": "tok-gabi-falso"}
        return 404, {"detail": f"rota falsa não prevista: {metodo} {rota}"}
