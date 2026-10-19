"""Cadastro das contas do Teams pelo painel (/api/v1/teams/fontes). Só o boss.
A API não tem rede nem segredo e nunca chama a ponte: só decide QUAIS contas o coletor lê. A auditoria leva só ids e nomes de estado, nunca o e-mail da conta.
Consome: teams.fontes."""
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.db import transacao
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro
from gabi.teams import fontes as fn

router = APIRouter(prefix="/api/v1/teams", dependencies=[Depends(exigir("boss"))])


def _audit(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'teams')", (dt.datetime.now(dt.timezone.utc).isoformat(), quem, o_que))


def _traduzir(e: fn.ErroFonte):
    if e.nao_encontrado:
        return erro(404, "nao_encontrado", str(e))
    return erro(409 if e.conflito else 400, "conflito" if e.conflito else "requisicao_invalida", str(e))


@router.get("/fontes")
def fontes(request: Request):
    """Contas do Teams cadastradas, com estado, última coleta, último erro e quantas conversas.
    `ultimo_erro` vem como o coletor gravou: pode ser um aviso mesmo numa coleta que deu certo (ex.: 'N chat(s) pulado(s) por erro'), então o painel mostra como aviso, não como falha."""
    con = _con(request)
    try:
        return envelope(con, {"fontes": fn.listar(con)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/fontes", status_code=201)
async def criar_fonte(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cadastra uma conta do Teams (e-mail). Nasce `a_decidir`: nada é lido até liberar."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                fid = fn.criar(con, corpo.get("conta"))
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"teams: cadastrou fonte {fid}")
        return envelope(con, {"id": fid}, agora=_agora(request))
    finally:
        con.close()


@router.put("/fontes/{fonte_id}/estado")
async def estado_fonte(fonte_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Libera (`sim`), desliga (`nao`) ou devolve para decisão (`a_decidir`) uma conta. Só liberada é lida pelo coletor."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                fn.definir_estado(con, fonte_id, corpo.get("estado"))
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"teams: fonte {fonte_id} -> {corpo['estado']}")
        return envelope(con, {"id": fonte_id, "estado": corpo["estado"]}, agora=_agora(request))
    finally:
        con.close()
