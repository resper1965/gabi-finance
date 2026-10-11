"""Contatos do Google (People API), SÓ leitura de nome e telefone. Só o serviço `gabi-brain-fontes` tem rede e segredos (R5); o resto do
brain chega aqui pela ponte (`PonteContatos`). Escopo `contacts.readonly`; `personFields=names,phoneNumbers` e nada mais (sem foto, e-mail,
endereço ou nota). Token por conta: OAuth do usuário com refresh token (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_<CONTA> no
ambiente do serviço). Segredo e corpo de resposta nunca entram em erro, log ou repr. Docs: docs/fontes/google.md."""
import urllib.parse
from typing import Callable

from gabi.fontes.google_oauth import (  # noqa: F401  (nomes reexportados: ponte, testes e escuta ainda os importam daqui)
    ErroGoogleOAuth, FOLGA_S, TOKEN_URL, TokenOAuth, _http_real, chamar as _chamar, conta_valida as _conta_valida,
    credenciais_do_ambiente, nome_da_variavel)

ESCOPO = "https://www.googleapis.com/auth/contacts.readonly"
URL_CONTATOS = "https://people.googleapis.com/v1/people/me/connections"
CAMPOS = "names,phoneNumbers"
MAX_PAGINAS = 200
ErroGoogleContatos = ErroGoogleOAuth  # alias: a ponte e os testes de contatos usam este nome


def _primeiro(lista):
    itens = [x for x in (lista or []) if isinstance(x, dict)]
    return sorted(itens, key=lambda x: not (isinstance(x.get("metadata"), dict) and x["metadata"].get("primary") is True))  # estável: o primário vem primeiro


def listar_contatos(conta: str, token: Callable[[str], str], http=_http_real) -> list[dict]:
    """Todas as páginas de people/me/connections -> [{nome, telefone}] (telefone cru; um item por telefone)."""
    conta = _conta_valida(conta)
    saida, pagina, vistas = [], None, set()
    for _ in range(MAX_PAGINAS):
        q = {"personFields": CAMPOS, "sources": "READ_SOURCE_TYPE_CONTACT", "pageSize": "1000"}
        if pagina:
            q["pageToken"] = pagina
        url = URL_CONTATOS + "?" + urllib.parse.urlencode(q, safe=",")
        status, resp = _chamar(http, "GET", url, None, {"Authorization": f"Bearer {token(conta)}"})
        if status == 401 and hasattr(token, "invalidar"):  # access token vencido/revogado: uma nova tentativa com token novo
            token.invalidar(conta)
            status, resp = _chamar(http, "GET", url, None, {"Authorization": f"Bearer {token(conta)}"})
        if status >= 400:
            raise ErroGoogleContatos(f"people.connections.list -> {status}")
        if not isinstance(resp, dict):
            raise ErroGoogleContatos("resposta inválida do Google")
        for p in resp.get("connections") or []:
            if not isinstance(p, dict):
                continue
            nomes = _primeiro(p.get("names"))
            nome = nomes[0].get("displayName") if nomes else None
            for t in _primeiro(p.get("phoneNumbers")):
                if isinstance(t.get("value"), str) and t["value"].strip():
                    item = {"nome": nome if isinstance(nome, str) and nome.strip() else None, "telefone": t["value"]}
                    if isinstance(t.get("canonicalForm"), str) and t["canonicalForm"].strip():
                        item["canonico"] = t["canonicalForm"].strip()  # E.164 vindo do Google
                    saida.append(item)
        pagina = resp.get("nextPageToken")
        if not pagina:
            return saida
        if pagina in vistas:
            break
        vistas.add(pagina)
    raise ErroGoogleContatos("paginação sem fim")


class GoogleContatos:
    """Objeto da ponte: `listar(conta)`. Sem o token provider nada sai."""

    def __init__(self, token: Callable[[str], str], http=_http_real):
        self._token, self._http = token, http

    def __repr__(self):
        return "GoogleContatos(<oculto>)"

    def listar(self, conta: str) -> list[dict]:
        return listar_contatos(conta, self._token, self._http)


def google_contatos_do_ambiente(env) -> GoogleContatos | None:
    """None ("não configurada") sem GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET."""
    cred = credenciais_do_ambiente(env)
    if cred is None:
        return None
    return GoogleContatos(TokenOAuth(cred[0], cred[1], env))
