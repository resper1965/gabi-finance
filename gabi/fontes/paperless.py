"""Cliente REST do Paperless-ngx: lê documentos e campos, adiciona etiquetas `gabi:*`. Docs: docs/fontes/paperless.md.

R2/R10: não existe método de exclusão (nem de remover etiqueta); só GET, POST (criar) e PATCH (acrescentar etiqueta).
R5: o token vem de quem instancia (arquivo de ambiente) e nunca entra em erro ou log. Consome: nada.
"""
import json
import secrets
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlencode

Http = Callable[..., "tuple[int, object]"]  # (metodo, url, corpo, cabecalhos) -> (status, json | bytes)

# permissões do usuário `gabi`: ver/criar/alterar; NENHUMA `delete_*`
PERMISSOES = ("view_document", "add_document", "change_document", "view_tag", "add_tag", "change_tag",
              "view_correspondent", "add_correspondent", "view_documenttype", "add_documenttype",
              "view_customfield", "add_customfield", "view_storagepath")
CAMPOS = ("CPF", "valor", "vencimento", "pessoa")  # campos personalizados que o app lê
TIPO_CAMPO = {"CPF": "string", "valor": "string", "vencimento": "date", "pessoa": "string"}


class ErroPaperless(Exception):
    pass


def _http_real(metodo, url, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
            return r.status, (json.loads(bruto) if "json" in (r.headers.get("Content-Type") or "") else bruto)
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.reason}
    except OSError as e:
        raise ErroPaperless(f"Paperless indisponível: {type(e).__name__}") from None


class Paperless:
    def __init__(self, base: str, token: str, *, http: Http | None = None):
        self.base, self.token, self._http = base.rstrip("/"), token, http or _http_real

    def _pedir(self, metodo, caminho, corpo=None, token=None):
        status, resp = self._http(metodo, self.base + caminho, corpo, {"Authorization": f"Token {token or self.token}"})
        if status >= 400:
            raise ErroPaperless(f"{metodo} {caminho.split('?')[0]} -> {status}")
        return resp

    def _paginas(self, caminho):
        url = self.base + caminho
        while url:
            status, resp = self._http("GET", url, None, {"Authorization": f"Token {self.token}"})
            if status >= 400:
                raise ErroPaperless(f"GET {caminho.split('?')[0]} -> {status}")
            yield from resp["results"]
            url = resp.get("next")

    def docs(self, **filtros) -> list[dict]:
        """Documentos (todas as páginas), com os filtros do Paperless como argumentos (ex.: tags__id__all=3, page_size=100)."""
        filtros.setdefault("page_size", 100)
        return list(self._paginas("/api/documents/?" + urlencode(filtros)))

    def baixar(self, id: int) -> bytes:
        return self._pedir("GET", f"/api/documents/{int(id)}/download/")

    def _etiqueta(self, nome: str) -> int:
        achada = next(iter(self._paginas("/api/tags/?" + urlencode({"name__iexact": nome}))), None)
        if achada:
            return achada["id"]
        return self._pedir("POST", "/api/tags/", {"name": nome})["id"]

    def etiquetar(self, id: int, tags: list[str]) -> None:
        """Acrescenta etiquetas `gabi:*` ao documento; nunca remove nem troca as que já existem."""
        if not tags or any(not t.startswith("gabi:") for t in tags):
            raise ValueError("o app só mexe em etiquetas gabi:*")
        doc = self._pedir("GET", f"/api/documents/{int(id)}/")
        ids = set(doc.get("tags") or []) | {self._etiqueta(t) for t in tags}
        self._pedir("PATCH", f"/api/documents/{int(id)}/", {"tags": sorted(ids)})

    def campos(self, id: int) -> dict:
        """CPF, valor, vencimento e pessoa do documento (campos personalizados); ausente = None."""
        nomes = {c["id"]: c["name"] for c in self._paginas("/api/custom_fields/")}
        doc = self._pedir("GET", f"/api/documents/{int(id)}/")
        por_nome = {nomes.get(c["field"]): c.get("value") for c in doc.get("custom_fields") or []}
        return {k: por_nome.get(k) for k in CAMPOS}

    def preparar_usuario(self, token_admin: str) -> str:
        """Com o token de administrador (usado só aqui, nunca guardado): cria os campos personalizados e o usuário `gabi`
        sem permissão de apagar; devolve o token do `gabi` para o chamador gravar no ambiente."""
        existentes = {c["name"] for c in self._paginas_admin("/api/custom_fields/", token_admin)}
        for nome in CAMPOS:
            if nome not in existentes:
                self._pedir("POST", "/api/custom_fields/", {"name": nome, "data_type": TIPO_CAMPO[nome]}, token_admin)
        senha = secrets.token_urlsafe(32)
        self._pedir("POST", "/api/users/", {"username": "gabi", "password": senha, "user_permissions": list(PERMISSOES),
                                            "is_active": True, "is_staff": False, "is_superuser": False}, token_admin)
        return self._pedir("POST", "/api/token/", {"username": "gabi", "password": senha}, token_admin)["token"]

    def _paginas_admin(self, caminho, token):
        resp = self._pedir("GET", caminho, None, token)
        return resp["results"]
