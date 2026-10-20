"""Escrita de contatos da ness no Graph: CRIAR, CORRIGIR (nome e celular), RENOMEAR, APAGAR UM TELEFONE e APAGAR O CONTATO (ADR-021), nada mais.
Fica fora de `graph_ness.py` para que a trava de leitura daquele arquivo continue valendo. Antes de alterar, relê o contato e só escreve se
o que o chamador viu (`antes`) ainda confere; senão devolve `alterado`. Erro nunca leva corpo de resposta, nome nem telefone."""
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
    dados = None if corpo is None else json.dumps(corpo).encode()
    for tentativa in (1, 2):
        cab = {"Authorization": f"Bearer {gr._token()}", **({} if dados is None else {"Content-Type": "application/json"})}
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


CAMPOS_TELEFONE = {"mobile": "mobilePhone", "home": "homePhones", "business": "businessPhones"}


def _url_contato(gr, conta, graph_id) -> str:
    base = _base(gr, conta)
    if not isinstance(graph_id, str) or not _ID_CONTATO.match(graph_id):
        raise ErroGraphNess("id de contato inválido")
    return f"{base}/{urllib.parse.quote(graph_id, safe='')}"


def renomear(gr, conta, graph_id, nome_antes, nome_depois) -> dict:
    """Troca só o displayName, se o contato ainda tiver `nome_antes`."""
    url = _url_contato(gr, conta, graph_id)
    nome_antes, nome_depois = _texto(nome_antes, MAX_NOME), _texto(nome_depois, MAX_NOME)
    atual = gr._get(f"{url}?$select=displayName")
    if atual.get("displayName") != nome_antes:
        return {"resultado": "alterado"}
    _escrever(gr, "PATCH", url, {"displayName": nome_depois})
    return {"resultado": "ok"}


def apagar_telefone(gr, conta, graph_id, campo, telefone_antes) -> dict:
    """Limpa só um telefone do campo `campo` (mobile/home/business), se ele ainda for `telefone_antes`; os outros números ficam."""
    url = _url_contato(gr, conta, graph_id)
    if campo not in CAMPOS_TELEFONE:
        raise ErroGraphNess("contato inválido")
    telefone_antes = _texto(telefone_antes, MAX_TELEFONE)
    atual = gr._get(f"{url}?$select=mobilePhone,homePhones,businessPhones")
    if campo == "mobile":
        if atual.get("mobilePhone") != telefone_antes:
            return {"resultado": "alterado"}
        corpo = {"mobilePhone": None}
    else:
        lista = atual.get(CAMPOS_TELEFONE[campo])
        if not isinstance(lista, list) or telefone_antes not in lista:
            return {"resultado": "alterado"}
        corpo = {CAMPOS_TELEFONE[campo]: [t for t in lista if t != telefone_antes]}
    _escrever(gr, "PATCH", url, corpo)
    return {"resultado": "ok"}


def apagar(gr, conta, graph_id, nome_antes, telefone_antes) -> dict:
    """Apaga o contato inteiro, só se ainda tiver `nome_antes`, nenhum e-mail e UM telefone, exatamente `telefone_antes` (o texto original que o
    dono viu): nunca apaga o que ganhou dado, trocou ou perdeu o número depois da proposta."""
    url = _url_contato(gr, conta, graph_id)
    nome_antes, telefone_antes = _texto(nome_antes, MAX_NOME), _texto(telefone_antes, MAX_TELEFONE)
    atual = gr._get(f"{url}?$select=displayName,mobilePhone,homePhones,businessPhones,emailAddresses")
    telefones = ([atual.get("mobilePhone")] if atual.get("mobilePhone") else []) + list(atual.get("homePhones") or []) + list(atual.get("businessPhones") or [])
    if atual.get("displayName") != nome_antes or atual.get("emailAddresses") or telefones != [telefone_antes]:
        return {"resultado": "alterado"}
    _escrever(gr, "DELETE", url, None)
    return {"resultado": "ok"}
