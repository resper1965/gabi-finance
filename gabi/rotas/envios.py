"""Envios (/api/v1/envios): fila de propostas do Hermes (evento de agenda, mensagem do Teams) que só saem depois do "Enviar" do dono. Só o boss.
A API não tem rede: o envio usa as fontes injetadas (fábricas `google_agenda` e `graph_ness`).
Consome: envios.propostas, envios.enviar."""
import asyncio

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.envios import enviar as ex
from gabi.envios import propostas as pr
from gabi.envios.propostas import ErroEnvio
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/envios", dependencies=[Depends(exigir("boss"))])

CONFLITOS = {"conflito", "vencida", "hash_diferente", "envios_desligados", "conta_nao_permitida"}
MENSAGENS = {
    "nao_encontrado": "envio não encontrado", "conflito": "o envio já foi decidido ou está em andamento",
    "vencida": "a proposta venceu", "hash_diferente": "a proposta mudou; recarregue a lista",
    "envios_desligados": "os envios estão desligados", "conta_nao_permitida": "a conta não está liberada para envios",
}


def _erro(e: ErroEnvio):
    if e.codigo == "nao_encontrado":
        return erro(404, "nao_encontrado", MENSAGENS["nao_encontrado"])
    if e.codigo in CONFLITOS:
        return erro(409, e.codigo, MENSAGENS[e.codigo])
    return erro(400, "requisicao_invalida", "requisição inválida")


def _fonte(request: Request, nome: str):
    fabrica = request.app.state.fontes.get(nome)
    return fabrica() if fabrica else None


@router.get("")
def listar_envios(request: Request, estado: str = "pendente"):
    """Propostas de envio (estado=pendente ou decididas) com o conteúdo legível e se a escrita está ligada."""
    if estado not in ("pendente", "decididas"):
        raise erro(400, "requisicao_invalida", "estado deve ser pendente ou decididas")
    con = _con(request)
    try:
        itens = pr.listar(con, _agora(request), estado)
        return envelope(con, {"itens": itens, "escrita": "ligado" if pr.escrita_ligada(con) else "desligado"}, agora=_agora(request))
    finally:
        con.close()


@router.post("/{envio_id}/enviar")
async def enviar_envio(envio_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Envia a proposta pendente (uma única tentativa) se o `hash` bater com o que o dono viu; devolve o estado final (enviada, falhou ou incerto)."""
    corpo = _corpo(await _json(request))
    h = corpo.get("hash")
    if not isinstance(h, str) or not h:
        raise erro(400, "requisicao_invalida", "hash é obrigatório")
    return await asyncio.to_thread(_enviar_sincrono, request, envio_id, h, ident.login)  # rede bloqueante (até ~130 s): fora do laço da API


def _enviar_sincrono(request: Request, envio_id: int, h: str, login: str):
    """Fábricas, conexão e envio no thread de trabalho: a conexão sqlite abre e fecha aqui (ela só vale no thread que a criou)."""
    google, graph = _fonte(request, "google_agenda"), _fonte(request, "graph_ness")
    con = _con(request)
    try:
        try:
            r = ex.enviar(con, envio_id, h, login, _agora(request), google, graph)
        except ErroEnvio as e:
            raise _erro(e) from None
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.post("/{envio_id}/recusar")
def recusar_envio(envio_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Recusa a proposta pendente; nada é enviado."""
    con = _con(request)
    try:
        try:
            pr.recusar(con, envio_id, ident.login, _agora(request))
        except ErroEnvio as e:
            raise _erro(e) from None
        return envelope(con, {"id": envio_id, "estado": "recusada"}, agora=_agora(request))
    finally:
        con.close()
