"""Escrita de contatos da ness no Graph: CRIAR e CORRIGIR (nome e celular), nada mais. Não existe apagar, nem tocar em outros campos.
Fica fora de `graph_ness.py` para que a trava de leitura daquele arquivo continue valendo. Antes de alterar, relê o contato e só escreve se
nome e celular ainda forem os que o chamador viu (`antes`); senão devolve `alterado`. Erro nunca leva corpo de resposta, nome nem telefone."""
import json
import urllib.parse

from gabi.fontes.graph_ness import _ID_CONTATO, BASE, ErroGraphNess, _chamar

MAX_NOME = 200
MAX_TELEFONE = 30


def _texto(v, maximo: int) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > maximo:
        raise ErroGraphNess("contato inválido")
    return v


def _par(d) -> tuple[str, str]:
    if not isinstance(d, dict):
        raise ErroGraphNess("contato inválido")
    return _texto(d.get("nome"), MAX_NOME), _texto(d.get("telefone"), MAX_TELEFONE)


def _escrever(gr, metodo: str, url: str, corpo: dict) -> tuple[int, object]:
    """Escrita autenticada; um 401 invalida o token e repete UMA vez (como o /move). Status >= 300 vira erro sem corpo."""
    dados = json.dumps(corpo).encode()
    for tentativa in (1, 2):
        cab = {"Authorization": f"Bearer {gr._token()}", "Content-Type": "application/json"}
        status, resp = _chamar(gr._http, metodo, url, dados, cab)
        if status == 401 and tentativa == 1 and hasattr(gr._token, "invalidar"):
            gr._token.invalidar()
            continue
        break
    if status >= 300:
        raise ErroGraphNess(f"contato: HTTP {status}")
    return status, resp


def _base(gr, conta) -> str:
    return f"{BASE}/users/{urllib.parse.quote(gr._conta(conta), safe='')}/contacts"


def criar(gr, conta, nome, telefone) -> dict:
    nome, telefone = _texto(nome, MAX_NOME), _texto(telefone, MAX_TELEFONE)
    base = _base(gr, conta)
    _, resp = _escrever(gr, "POST", base, {"displayName": nome, "mobilePhone": telefone})
    novo = resp.get("id") if isinstance(resp, dict) else None
    if not isinstance(novo, str) or not _ID_CONTATO.match(novo):
        raise ErroGraphNess("resposta inválida do Graph")
    return {"id": novo}


def corrigir(gr, conta, graph_id, antes, depois) -> dict:
    base = _base(gr, conta)
    if not isinstance(graph_id, str) or not _ID_CONTATO.match(graph_id):
        raise ErroGraphNess("id de contato inválido")
    if not isinstance(antes, dict) or not isinstance(antes.get("nome"), str) or not isinstance(antes.get("telefone"), str):
        raise ErroGraphNess("contato inválido")
    nome, telefone = _par(depois)
    url = f"{base}/{urllib.parse.quote(graph_id, safe='')}"
    atual = gr._get(f"{url}?$select=displayName,mobilePhone")
    if atual.get("displayName") != antes["nome"] or atual.get("mobilePhone") != antes["telefone"]:
        return {"resultado": "alterado"}
    _escrever(gr, "PATCH", url, {"displayName": nome, "mobilePhone": telefone})
    return {"resultado": "ok"}
