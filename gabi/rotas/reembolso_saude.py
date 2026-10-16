"""Rota /api/v1/reembolso-saude: dossiês de reembolso do plano de saúde COM os nomes (paciente e prestador), lidos do cofre cifrado (ADR-014).
Só boss com grau total em saúde; o acesso entra no log `leitura` do cofre. Valor, CPF/CNPJ e conselho NÃO saem daqui. As ferramentas MCP não têm a chave e
falam só do número do dossiê; esta é a forma de saber quem é cada um. Consome: reembolso_saude.{cofre,dossies,requisitos}, identidade."""
import threading
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.familia.saude import _log, abrir_saude
from gabi.identidade import Identidade, exigir_informacao
from gabi.mcp.ferramentas_reembolso import _registrar
from gabi.mcp.ferramentas_prop import ErroFerramenta
from gabi.reembolso_saude import cofre, dossies, requisitos, texto
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

BRT = ZoneInfo("America/Sao_Paulo")

router = APIRouter(prefix="/api/v1/reembolso-saude")
_TRAVA = threading.Lock()  # o cofre é regravado inteiro: um escritor por vez neste processo


@router.get("/dossies")
def listar(request: Request, ident: Identidade = Depends(exigir_informacao("saúde", "total"))):
    """Dossiês (número, paciente, prestador, mês, estado, o que falta e os documentos com tipo e estado); o acesso fica no log de saúde."""
    cfg = getattr(request.app.state, "saude", None)
    if not cfg:
        raise erro(503, "fonte_indisponivel", "o arquivo de saúde não está configurado (falta a chave)")
    con = _con(request)
    try:
        req = requisitos.carregar(con)
        hoje = _agora(request).date()
        parados = {r["id"]: r["parado_desde"] for r in con.execute("select id, parado_desde from reembolso_saude_dossie")}
        with _TRAVA, abrir_saude(*cfg) as s:
            _log(s, ident.login, None, "reembolso:dossies")
            docs, nomes = cofre.docs(s), {d["id"]: d for d in cofre.dossies_todos(s)}
        faltam = {x["docs"][0]: x["faltam"] for x in dossies.resumo([d for d in docs if d["estado"] == "a_pedir"], hoje, req)}
        itens = []
        for did, dos in sorted(nomes.items()):
            ds = [d for d in docs if d["dossie_id"] == did]
            if not ds or all(d["estado"] == "autorizacao" for d in ds):
                continue
            falta = next((faltam[d["id"]] for d in ds if d["id"] in faltam), [])
            itens.append({"dossie": did, "paciente": dos["paciente"], "prestador": dos["prestador"], "mes": dos["mes"], "parado_desde": parados.get(did),
                          "estado": next(e for e in ("a_pedir", "sem_nf", "sem_aprovacao", "a_conferir", "pedido", "recebido") if any(d["estado"] == e for d in ds)),
                          "faltam": [requisitos.rotulo(req, i) for i in falta],
                          "documentos": [{"id": d["id"], "documento": d["documento"], "caso": d["caso"], "estado": d["estado"], "data": d["data"].isoformat()} for d in ds]})
        return envelope(con, {"dossies": itens}, agora=_agora(request))
    finally:
        con.close()


@router.get("/semana")
def semana(request: Request, ident: Identidade = Depends(exigir_informacao("saúde", "total"))):
    """Texto da lista de segunda ("Resumo da semana"), o mesmo da ferramenta MCP e do aviso; sem nomes (lê só a projeção do `gabi.db`)."""
    con = _con(request)
    try:
        linhas = texto.montar_segunda(con, _agora(request).astimezone(BRT).date())
        return envelope(con, {"linhas": linhas, "texto": "\n".join(linhas)}, agora=_agora(request))
    finally:
        con.close()


async def _acao(request: Request, dossie_id: int, acao: str):
    """Grava a INTENÇÃO (tabela `reembolso_saude_acao`); o cofre só muda na próxima rodada. Não envia nada (R2). Mesma gravação das ferramentas MCP."""
    corpo = {}
    if request.headers.get("content-length") not in (None, "0"):
        corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            r = _registrar(con, _agora(request), dossie_id, acao, corpo.get("protocolo") if acao == "pedi" else None)
        except ErroFerramenta as e:
            raise erro(404, "nao_encontrado", str(e))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.post("/dossies/{dossie_id}/pedi")
async def pedi(dossie_id: int, request: Request, ident: Identidade = Depends(exigir_informacao("saúde", "total"))):
    """"Marquei como pedido": registra que o Ricardo pediu (corpo opcional `{protocolo}`); aplica na próxima rodada."""
    return await _acao(request, dossie_id, "pedi")


@router.post("/dossies/{dossie_id}/recebi")
async def recebi(dossie_id: int, request: Request, ident: Identidade = Depends(exigir_informacao("saúde", "total"))):
    """"Recebi": registra que o reembolso chegou; aplica na próxima rodada."""
    return await _acao(request, dossie_id, "recebi")
