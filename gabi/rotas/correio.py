"""Painel do correio (/api/v1/correio): contas, parâmetros, fila de prioridades, lixeira e restaurar. Só o boss.
A API não tem rede nem segredo: restaurar passa pela ponte do serviço de fontes. A auditoria leva só ids e nomes de chave, nunca valores,
remetente nem assunto. Consome: correio.fontes, correio.consulta, correio.processar."""
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.correio import consulta
from gabi.correio import fontes as fn
from gabi.correio.processar import fechar_alerta
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/correio", dependencies=[Depends(exigir("boss"))])


def _audit(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'correio')", (dt.datetime.now(dt.timezone.utc).isoformat(), quem, o_que))


def _traduzir(e: fn.ErroFonte):
    if e.nao_encontrado:
        return erro(404, "nao_encontrado", str(e))
    return erro(409 if e.conflito else 400, "conflito" if e.conflito else "requisicao_invalida", str(e))


@router.get("/fontes")
def fontes(request: Request):
    """Contas de e-mail cadastradas: leitura (estado) e lixeira separadas, última sincronização, último erro e contagens."""
    con = _con(request)
    try:
        return envelope(con, {"fontes": fn.listar(con)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/fontes")
async def criar_fonte(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cadastra uma conta (e-mail e provedor google|graph). Nasce `a_decidir` e sem lixeira: nada é lido nem movido até liberar."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                fid = fn.criar(con, corpo.get("conta"), corpo.get("provedor", "google"))
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"correio: cadastrou conta {fid}")
        return envelope(con, {"id": fid, "estado": "a_decidir", "lixeira": 0}, agora=_agora(request))
    finally:
        con.close()


@router.patch("/fontes/{fonte_id}")
async def alterar_fonte(fonte_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Libera ou desliga a leitura (`estado`) e liga ou desliga a lixeira (`lixeira`); a lixeira exige a leitura liberada."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                novo = fn.alterar(con, fonte_id, corpo)
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            _audit(con, ident.login, f"correio: conta {fonte_id} → estado {novo['estado']}, lixeira {novo['lixeira']}")
        return envelope(con, novo, agora=_agora(request))
    finally:
        con.close()


@router.get("/parametros")
def parametros(request: Request):
    """Critérios de emergência, VIPs, limiar da lixeira, janela de leitura e retenção do trecho (padrões se não definidos)."""
    con = _con(request)
    try:
        return envelope(con, fn.parametros(con), agora=_agora(request))
    finally:
        con.close()


@router.put("/parametros")
async def gravar_parametros(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Grava só os parâmetros enviados; valida faixas e audita só os nomes das chaves (nunca critérios nem VIPs)."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        with transacao(con):
            try:
                novos = fn.validar_parametros(corpo)
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            fn.gravar_parametros(con, novos)
            _audit(con, ident.login, "correio: alterou parâmetros " + ", ".join(sorted(fn.CHAVES[k] for k in novos)))
        return envelope(con, fn.parametros(con), agora=_agora(request))
    finally:
        con.close()


@router.get("/prioridades")
def prioridades(request: Request):
    """Emergenciais e importantes em aberto, o emergencial primeiro (só de contas liberadas)."""
    con = _con(request)
    try:
        return envelope(con, {"mensagens": consulta.importantes(con, limite=50, agora=_agora(request))}, agora=_agora(request))
    finally:
        con.close()


@router.get("/lixeira")
def lixeira(request: Request):
    """O que a Gabi mandou para a lixeira nos últimos 30 dias, para restaurar."""
    con = _con(request)
    try:
        return envelope(con, {"mensagens": consulta.na_lixeira(con, agora=_agora(request))}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/restaurar")
async def restaurar(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Tira da lixeira (pela ponte) e marca `restaurada`: a Gabi nunca a move de novo. Idempotente. 503 `fonte_indisponivel` se a ponte ou o Gmail não confirmar."""
    await _json(request)
    con = _con(request)
    try:
        m = con.execute("select m.id, m.externo_id, m.thread_id, m.estado, f.conta from email_msg m join email_fonte f on f.id=m.fonte_id where m.id=?", (mensagem_id,)).fetchone()
        if m is None:
            raise erro(404, "nao_encontrado", "mensagem não existe")
        if m["estado"] == "restaurada":
            return envelope(con, {"id": mensagem_id, "estado": "restaurada"}, agora=_agora(request))
        if m["estado"] != "na_lixeira":
            raise erro(409, "conflito", "a mensagem não está na lixeira")
        fabrica = request.app.state.fontes.get("google_email")
        fonte = fabrica() if fabrica else None
        if fonte is None:
            raise erro(503, "fonte_indisponivel", "o e-mail do Google não está configurado")
        try:
            resultado = fonte.restaurar(m["conta"], [m["externo_id"]])
        except ErroGoogleOAuth as e:
            raise erro(503, "fonte_indisponivel", str(e)) from None
        if not isinstance(resultado, dict) or resultado.get(m["externo_id"]) != "ok":
            raise erro(503, "fonte_indisponivel", "o Gmail não confirmou a restauração; tente de novo")
        agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
        with transacao(con):
            con.execute("update email_msg set estado='restaurada', atualizado_em=? where id=?", (agora, mensagem_id))
            fechar_alerta(con, m["thread_id"] or m["externo_id"], agora)
            _audit(con, ident.login, f"correio: restaurou mensagem {mensagem_id}")
        return envelope(con, {"id": mensagem_id, "estado": "restaurada"}, agora=_agora(request))
    finally:
        con.close()
