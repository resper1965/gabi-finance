"""Fontes e parâmetros da agenda pelo painel (/api/v1/agenda/fontes, /api/v1/agenda/parametros). Só o boss.
A API não tem rede nem segredo: descobrir calendários passa pela ponte do serviço de fontes. A auditoria leva só ids e nomes de chave, nunca valores nem títulos.
(GET /api/v1/agenda — os compromissos — fica em `gabi.rotas.dia`.) Consome: agenda.fontes."""
import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.agenda import fontes as fn
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/agenda", dependencies=[Depends(exigir("boss"))])


def _audit(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'agenda')", (dt.datetime.now(dt.timezone.utc).isoformat(), quem, o_que))


def _traduzir(e: fn.ErroFonte):
    if e.nao_encontrado:
        return erro(404, "nao_encontrado", str(e))
    return erro(409 if e.conflito else 400, "conflito" if e.conflito else "requisicao_invalida", str(e))


@router.get("/fontes")
def fontes(request: Request):
    """Contas e calendários de agenda cadastrados, com estado, última sincronização, último erro e quantos eventos."""
    con = _con(request)
    try:
        return envelope(con, {"fontes": fn.listar(con)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/fontes")
async def criar_fonte(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cadastra uma conta de agenda (e-mail, provedor google|graph, auth oauth|delegacao). Nasce `a_decidir`: nada é lido até liberar."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                fid = fn.criar(con, corpo.get("conta"), corpo.get("provedor"), corpo.get("auth", "oauth"))
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"agenda: cadastrou fonte {fid}")
        return envelope(con, {"id": fid, "estado": "a_decidir"}, agora=_agora(request))
    finally:
        con.close()


@router.post("/fontes/{fonte_id}/calendarios/descobrir")
async def descobrir(fonte_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Pergunta ao Google ou ao Graph (pela ponte) quais calendários a conta enxerga e cadastra cada um como `a_decidir`. 503 `fonte_indisponivel` se a ponte ou a conta estiver fora."""
    await _json(request)
    con = _con(request)
    try:
        try:
            f = fn._existe(con, fonte_id)  # 404 antes de 503 e de qualquer chamada de rede
            nome, rotulo = ("graph_ness", "Microsoft (Graph)") if f["provedor"] == "graph" else ("google_agenda", "Google")
            fabrica = request.app.state.fontes.get(nome)
            fonte = fabrica() if fabrica else None
            if fonte is None:
                raise erro(503, "fonte_indisponivel", f"a agenda do {rotulo} não está configurada")
            achados = await asyncio.to_thread(fonte.listar_calendarios, f["conta"])  # rede bloqueante: fora do laço da API
        except fn.ErroFonte as e:
            raise _traduzir(e) from None
        except (ErroGoogleOAuth, ErroGraphNess) as e:
            raise erro(503, "fonte_indisponivel", str(e)) from None
        with transacao(con):
            try:
                cals = fn.descobrir_calendarios(con, fonte_id, lambda _conta: achados)
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            except ErroGoogleOAuth as e:
                raise erro(503, "fonte_indisponivel", str(e)) from None
            _audit(con, ident.login, f"agenda: descobriu {len(cals)} calendário(s) da fonte {fonte_id}")
        return envelope(con, {"calendarios": cals}, agora=_agora(request))
    finally:
        con.close()


@router.patch("/fontes/{fonte_id}")
async def alterar_fonte(fonte_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Libera (`sim`), desliga (`nao`) ou devolve para decisão (`a_decidir`) uma fonte. Só liberada é lida pelo timer."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                fn.definir_estado(con, fonte_id, corpo.get("estado"))
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"agenda: fonte {fonte_id} → {corpo['estado']}")
        return envelope(con, {"id": fonte_id, "estado": corpo["estado"]}, agora=_agora(request))
    finally:
        con.close()


@router.get("/parametros")
def parametros(request: Request):
    """Parâmetros da agenda: privados (mostrar|so_painel|ocultar), fuso e janela de leitura em dias (padrões se não definidos)."""
    con = _con(request)
    try:
        return envelope(con, fn.parametros(con), agora=_agora(request))
    finally:
        con.close()


@router.put("/parametros")
async def gravar_parametros(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Grava só os parâmetros enviados; valida faixas e audita só os nomes das chaves."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                novos = fn.validar_parametros(corpo)
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            fn.gravar_parametros(con, novos)
            con.execute("update agenda_fonte set recarga_em=null")  # dia local, título mascarado e janela estão gravados com o valor antigo: a próxima rodada recarrega tudo
            _audit(con, ident.login, "agenda: alterou parâmetros " + ", ".join(sorted(fn.CHAVES[k] for k in novos)))
        return envelope(con, fn.parametros(con), agora=_agora(request))
    finally:
        con.close()
