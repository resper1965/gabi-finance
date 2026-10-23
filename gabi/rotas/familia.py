"""Família (/api/v1/familia): fichas, propostas de documento, histórico de contato e vencimentos. Só o boss.
Os números dos documentos saem apenas em `GET /fichas/{id}` e `GET /propostas` (atual e proposto, a tela Família); o resto nunca os leva.
Consome: familia.fichas, familia.contato, familia.documentos, parametro `paperless.url`."""
import json

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.familia import contato as ct
from gabi.familia import documentos as dc
from gabi.familia import fichas as fi
from gabi.familia.fichas import ErroFamilia
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/familia", dependencies=[Depends(exigir("boss"))])

MENSAGENS = {
    "nao_encontrado": "não encontrado", "conflito": "o registro já foi decidido ou o valor mudou depois",
}


def _erro(e: ErroFamilia):
    if e.codigo == "nao_encontrado":
        return erro(404, "nao_encontrado", MENSAGENS["nao_encontrado"])
    if e.codigo == "conflito":
        return erro(409, "conflito", MENSAGENS["conflito"])
    return erro(400, e.codigo, "requisição inválida")


def _paperless_url(con):
    r = con.execute("select valor from parametro where chave='paperless.url'").fetchone()
    if r is None:
        return None
    try:
        v = json.loads(r["valor"])
    except (TypeError, ValueError):
        return None
    return v if isinstance(v, str) and v else None


@router.get("/fichas")
def listar_fichas(request: Request):
    """Quem está no cadastro, sem número de documento."""
    con = _con(request)
    try:
        return envelope(con, {"itens": fi.listar(con)}, agora=_agora(request))
    finally:
        con.close()


@router.get("/fichas/{pessoa_id}")
def ficha_da_pessoa(pessoa_id: str, request: Request):
    """Ficha completa, com os números dos documentos, e a URL base do Paperless (ou null) para os links."""
    con = _con(request)
    try:
        try:
            f = fi.ficha(con, pessoa_id)
        except ErroFamilia as e:
            raise _erro(e) from None
        f["paperless_url"] = _paperless_url(con)
        return envelope(con, f, agora=_agora(request))
    finally:
        con.close()


@router.get("/propostas")
def listar_propostas(request: Request, estado: str = "pendente"):
    """Propostas de documento no estado dado, com o documento atual e o proposto."""
    con = _con(request)
    try:
        try:
            itens = dc.listar_propostas(con, estado)
        except ErroFamilia as e:
            raise _erro(e) from None
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/propostas/{proposta_id}/decisao")
async def decidir_proposta(proposta_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova ou recusa a proposta pendente (`{"estado": "aprovada"|"recusada"}`)."""
    corpo = _corpo(await _json(request))
    estado = corpo.get("estado")
    if not isinstance(estado, str):
        raise erro(400, "requisicao_invalida", "estado é obrigatório")
    con = _con(request)
    try:
        try:
            r = dc.decidir(con, proposta_id, estado, ident.login, _agora(request))
        except ErroFamilia as e:
            raise _erro(e) from None
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.get("/historico")
def historico_de_contato(request: Request, pessoa: str | None = None):
    """Mudanças de contato, da mais nova para a mais antiga; `pessoa` filtra pelo id."""
    con = _con(request)
    try:
        return envelope(con, {"itens": ct.historico(con, pessoa or None)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/historico/{historico_id}/desfazer")
def desfazer_mudanca(historico_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Restaura o valor anterior se o contato ainda estiver como a mudança deixou (senão 409)."""
    con = _con(request)
    try:
        try:
            r = ct.desfazer(con, historico_id, ident.login, _agora(request))
        except ErroFamilia as e:
            raise _erro(e) from None
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.get("/vencimentos")
def listar_vencimentos(request: Request, meses: int = 12):
    """Documentos que vencem nos próximos `meses` (e os vencidos há até 30 dias), sem número."""
    if not 1 <= meses <= 120:
        raise erro(400, "requisicao_invalida", "meses deve ficar entre 1 e 120")
    con = _con(request)
    try:
        agora = _agora(request)
        return envelope(con, {"itens": fi.vencimentos(con, agora.date(), meses)}, agora=agora)
    finally:
        con.close()
