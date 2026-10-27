"""Atividades (/api/v1/atividades): o to-do pessoal do Ricardo (ADR-033): listar, criar, concluir, cancelar e adiar.

Só chama `gabi.atividades` (as regras moram lá); `quem` = login, `origem` = 'painel'. `LookupError` → 404 `nao_encontrado`; `ValueError` → 400 `requisicao_invalida`.
Data e hora em Brasília (`AAAA-MM-DD` ou `AAAA-MM-DDTHH:MM`). Consome: atividades, envelope, identidade."""
from typing import Callable

from fastapi import APIRouter, Depends, Request

from gabi import atividades
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/atividades", dependencies=[Depends(exigir("boss"))])


def _so(corpo: dict, permitidos: set) -> None:
    extra = set(corpo) - permitidos
    if extra:
        raise erro(400, "requisicao_invalida", f"campos desconhecidos: {sorted(extra)}")


def _texto(corpo: dict, campo: str, obrigatorio: bool):
    v = corpo.get(campo)
    if v is None and not obrigatorio:
        return None
    if not isinstance(v, str):
        raise erro(400, "requisicao_invalida", f"{campo} deve ser texto")
    return v


def _rodar(request: Request, faz: Callable) -> dict:
    """Roda a regra com a conexão e devolve o envelope; traduz os erros das regras para HTTP."""
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
def listar(request: Request, status: str = "aberta"):
    """Atividades por status (aberta, feita ou cancelada), vencidas primeiro, com o prazo (vencida, hoje, proxima, sem_data)."""
    if status not in ("aberta", "feita", "cancelada"):
        raise erro(400, "requisicao_invalida", "status deve ser aberta, feita ou cancelada")
    return _rodar(request, lambda con, agora: {"itens": atividades.listar(con, agora, status)})


@router.post("", status_code=201)
async def criar(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria uma atividade: `texto` e, opcional, `vence_em` (AAAA-MM-DD ou AAAA-MM-DDTHH:MM). Igual a uma aberta devolve a existente (`ja_existia`)."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"texto", "vence_em"})
    texto, vence = _texto(corpo, "texto", True), _texto(corpo, "vence_em", False)
    return _rodar(request, lambda con, agora: atividades.criar(con, agora, ident.login, "painel", texto, vence))


@router.post("/{id_}/concluir")
def concluir(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Marca como feita (repetir não muda nada; não há reabrir)."""
    return _rodar(request, lambda con, agora: atividades.concluir(con, agora, ident.login, "painel", id_))


@router.post("/{id_}/cancelar")
def cancelar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cancela (excluir da lista); atividade já feita não pode ser cancelada."""
    return _rodar(request, lambda con, agora: atividades.cancelar(con, agora, ident.login, "painel", id_))


@router.patch("/{id_}")
async def adiar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Adia: novo `vence_em` (AAAA-MM-DD ou AAAA-MM-DDTHH:MM), só de atividade aberta e no futuro."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"vence_em"})
    vence = _texto(corpo, "vence_em", True)
    return _rodar(request, lambda con, agora: atividades.adiar(con, agora, ident.login, "painel", id_, vence))
