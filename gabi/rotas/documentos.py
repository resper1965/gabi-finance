"""Documentos (/api/v1/documentos): propostas e decisão (com correção e troca de titular), titulares com documentos e contato,
vencimentos. Só o boss; os números saem completos (decisão do dono), mas a auditoria (`decisao`) e os erros nunca os levam.
Consome: documentos.repositorio, familia.fichas (contato da pessoa), parametro `paperless.url`."""
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from gabi.documentos import repositorio as rp
from gabi.documentos.repositorio import ErroDocumentos
from gabi.envelope import envelope
from gabi.familia import fichas as fi
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro
from gabi.rotas.familia import _paperless_url

BRT = ZoneInfo("America/Sao_Paulo")
router = APIRouter(prefix="/api/v1/documentos", dependencies=[Depends(exigir("boss"))])

MENSAGENS = {
    "nao_encontrado": (404, "não encontrado"), "conflito": (409, "a proposta já foi decidida"),
    "titular_invalido": (400, "titular inexistente ou inválido"), "valor_invalido": (400, "valor inválido"),
}


def _erro(e: ErroDocumentos):
    status, mensagem = MENSAGENS.get(e.codigo, (400, "requisição inválida"))
    return erro(status, e.codigo, mensagem)


@router.get("/propostas")
def listar_propostas(request: Request, estado: str = "pendente"):
    """Propostas de documento no estado dado (titular ou bem novo, motivos de conferir, documento atual) e a URL base do Paperless.

    `titular` é null quando o documento cria um bem novo (`bem_novo`); `paperless_url` é null se não configurada."""
    con = _con(request)
    try:
        try:
            itens = rp.listar_propostas(con, estado)
        except ErroDocumentos as e:
            raise _erro(e) from None
        return envelope(con, {"itens": itens, "paperless_url": _paperless_url(con)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/propostas/{proposta_id}/decisao")
async def decidir_proposta(proposta_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova ou recusa a proposta pendente; `correcao` opcional troca campos (inclusive o titular) antes de aprovar; já decidida: 409.

    Corpo: `{"estado": "aprovada" ou "recusada", "correcao"?: {campo: valor}}`."""
    corpo = _corpo(await _json(request))
    estado, correcao = corpo.get("estado"), corpo.get("correcao")
    if not isinstance(estado, str):
        raise erro(400, "requisicao_invalida", "estado é obrigatório")
    con = _con(request)
    try:
        try:
            r = rp.decidir(con, proposta_id, estado, ident.login, _agora(request), correcao=correcao)
        except ErroDocumentos as e:
            raise _erro(e) from None
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.get("/titulares")
def listar_titulares(request: Request):
    """Pessoas (com contato) e bens ativos, cada um com os documentos ativos (números completos), e a URL base do Paperless."""
    con = _con(request)
    try:
        por: dict = {}
        for d in rp.consultar(con):
            por.setdefault((d["titular_tipo"], d["titular_id"]), []).append(d)
        pessoas = []
        for p in fi.listar(con):
            f = fi.ficha(con, p["id"])
            pessoas.append({k: f[k] for k in ("id", "nome", "nome_completo", "apelido", "parentesco", "nascimento", "telefones", "emails",
                                              "enderecos")} | {"documentos": por.get(("pessoa", p["id"]), [])})
        bens = [{k: b[k] for k in ("id", "tipo", "nome", "dados")} | {"documentos": por.get(("bem", b["id"]), [])} for b in rp.bens(con)]
        return envelope(con, {"pessoas": pessoas, "bens": bens, "paperless_url": _paperless_url(con)}, agora=_agora(request))
    finally:
        con.close()


@router.get("/vencimentos")
def listar_vencimentos(request: Request, meses: int = 12):
    """Documentos cuja última data (validade, fim de vigência, vencimento) cai nos próximos `meses` ou venceu há até 30 dias.

    "Hoje" é a data de Brasília, como no MCP."""
    if not 1 <= meses <= 120:
        raise erro(400, "requisicao_invalida", "meses deve ficar entre 1 e 120")
    con = _con(request)
    try:
        agora = _agora(request)
        return envelope(con, {"itens": rp.vencimentos(con, agora.astimezone(BRT).date(), meses)}, agora=agora)
    finally:
        con.close()
