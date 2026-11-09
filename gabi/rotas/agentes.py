"""Agentes externos (/api/v1/agentes, ADR-036): chaves do MCP — listar, criar, trocar escopos, revogar, rotacionar, chamadas e dados de conexão.

Só chama `gabi.agentes`; `quem` = login do painel. A `chave` (segredo) sai apenas nas respostas de criar e rotacionar, nunca em GET nem na `decisao`.
`LookupError` → 404 `nao_encontrado`; `ValueError` → 400 `requisicao_invalida`. Consome: agentes, envelope, identidade."""
from typing import Callable

from fastapi import APIRouter, Depends, Request

from gabi import agentes
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/agentes", dependencies=[Depends(exigir("boss"))])


def _so(corpo: dict, permitidos: set) -> None:
    extra = set(corpo) - permitidos
    if extra:
        raise erro(400, "requisicao_invalida", f"campos desconhecidos: {sorted(extra)}")


def _escopos(corpo: dict, obrigatorio: bool):
    v = corpo.get("escopos")
    if v is None and not obrigatorio:
        return None
    if not isinstance(v, list) or not all(isinstance(e, str) for e in v):
        raise erro(400, "requisicao_invalida", "escopos deve ser uma lista de textos")
    return v


def _rodar(request: Request, faz: Callable) -> dict:
    con = _con(request)
    try:
        try:
            dados = faz(con, _agora(request))
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e).strip("'\""))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


@router.get("")
def listar(request: Request):
    """Chaves (ativas e revogadas) com escopos, último uso e chamadas dos últimos 7 dias; nunca o segredo."""
    return _rodar(request, lambda con, agora: {"itens": agentes.listar_agentes(con, agora)})


@router.post("", status_code=201)
async def criar(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Emite uma chave: `nome` e, opcional, `escopos` (padrão do Hermes, sem sensível). A `chave` aparece só nesta resposta."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"nome", "escopos"})
    nome = corpo.get("nome")
    if not isinstance(nome, str):
        raise erro(400, "requisicao_invalida", "nome deve ser texto")
    escopos = _escopos(corpo, False)
    return _rodar(request, lambda con, agora: agentes.criar(con, agora, ident.login, nome, escopos))


@router.get("/conexao")
def conexao(request: Request):
    """URL do MCP e escopos (padrão e válidos) para montar a conexão do agente."""
    return _rodar(request, lambda con, agora: agentes.conexao(con))


@router.patch("/{id_}/escopos")
async def escopos(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Troca os escopos de uma chave ativa; o segredo não muda."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"escopos"})
    novos = _escopos(corpo, True)
    return _rodar(request, lambda con, agora: agentes.trocar_escopos(con, agora, ident.login, id_, novos))


@router.post("/{id_}/revogar")
def revogar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Revoga a chave (repetir não muda nada)."""
    return _rodar(request, lambda con, agora: agentes.revogar_agente(con, agora, ident.login, id_))


@router.post("/{id_}/rotacionar")
def rotacionar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Emite chave nova (mesmo nome e escopos) e revoga a antiga. A `chave` nova aparece só nesta resposta."""
    return _rodar(request, lambda con, agora: agentes.rotacionar(con, agora, ident.login, id_))


@router.get("/{id_}/chamadas")
def chamadas(id_: int, request: Request):
    """Últimas chamadas da chave: quando, ferramenta e status (nunca os argumentos)."""
    return _rodar(request, lambda con, agora: {"itens": agentes.chamadas(con, id_)})
