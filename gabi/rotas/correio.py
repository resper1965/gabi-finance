"""Painel do correio (/api/v1/correio): contas, parâmetros, fila de prioridades, lixeira, restaurar, lixo sugerido (mover/"não é lixo") e dispensar. Só o boss.
Mover usa SÓ trash (recuperável); a API nunca apaga e-mail de vez.
A API não tem rede nem segredo: restaurar passa pela ponte do serviço de fontes. A auditoria leva só ids e nomes de chave, nunca valores,
remetente nem assunto. Consome: correio.fontes, correio.consulta, correio.processar."""
import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, Request

from gabi.correio import consulta
from gabi.correio import fontes as fn
from gabi.correio import lixeira as lixeira_mod
from gabi.correio.regras import endereco
from gabi.correio.processar import fechar_alerta
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

_FONTE_EMAIL = {"google": "google_email", "graph": "graph_email"}  # chave de `app.state.fontes` por provedor da conta

_RECUSA_LIXEIRA = {"nao_triada": "só dá para mover o que o modelo sugeriu como lixo e continua na caixa",
                   "conta_desligada": "a conta está desligada",
                   "conta_sem_lixeira": "ligue a lixeira desta conta (Cadastros › E-mail) para mover"}  # mensagem da rota por código de `lixeira.planejar`

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


@router.get("/lixo-sugerido")
def lixo_sugerido(request: Request):
    """Lixo que o modelo apontou e NÃO foi movido (lixeira desligada na conta, confiança baixa, remetente protegido). Só sugestão: o dono decide."""
    con = _con(request)
    try:
        return envelope(con, {"mensagens": consulta.lixo_sugerido(con, agora=_agora(request))}, agora=_agora(request))
    finally:
        con.close()


@router.get("/dispensadas")
def dispensadas(request: Request):
    """O que o dono dispensou nos últimos 30 dias, para desfazer."""
    con = _con(request)
    try:
        return envelope(con, {"mensagens": consulta.dispensadas(con, agora=_agora(request))}, agora=_agora(request))
    finally:
        con.close()


def _mensagem(con, mensagem_id: int):
    m = con.execute("select m.id, m.externo_id, m.thread_id, m.estado, m.classe, m.dispensada_em, f.conta, f.provedor, f.estado as conta_estado, f.lixeira as conta_lixeira "
                    "from email_msg m join email_fonte f on f.id=m.fonte_id where m.id=?", (mensagem_id,)).fetchone()
    if m is None:
        raise erro(404, "nao_encontrado", "mensagem não existe")
    return m


@router.post("/mensagens/{mensagem_id}/lixeira")
async def mover_para_lixeira(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Decisão do dono sobre um "lixo sugerido": manda para a lixeira do Gmail (só trash, recuperável) e marca `na_lixeira`. Exige a conta liberada e a lixeira
    dela ligada. Idempotente. 404 antes de 409 antes de 503 `fonte_indisponivel` (ponte ou Gmail não confirmou)."""
    await _json(request)
    con = _con(request)
    try:
        _mensagem(con, mensagem_id)  # 404 se não existe
        lotes, falhas, ja = lixeira_mod.planejar(con, [mensagem_id], so_lixo=True)
        if ja:
            return envelope(con, {"id": mensagem_id, "estado": "na_lixeira"}, agora=_agora(request))
        if falhas:
            raise erro(409, "conflito", _RECUSA_LIXEIRA[falhas[0]["codigo"]])
        (provedor, conta, _fonte), itens = next(iter(lotes.items()))
        fabrica = request.app.state.fontes.get(_FONTE_EMAIL[provedor])
        fonte = fabrica() if fabrica else None
        if fonte is None:
            raise erro(503, "fonte_indisponivel", "o e-mail do Google não está configurado")
        ok, falhas_rede = await asyncio.to_thread(lixeira_mod.aplicar, fonte, conta, itens)  # rede bloqueante: fora do laço da API
        if falhas_rede or not ok:
            raise erro(503, "fonte_indisponivel", "o Gmail não confirmou o movimento; tente de novo")
        with transacao(con):
            lixeira_mod.marcar(con, [mensagem_id], _agora(request))
            _audit(con, ident.login, f"correio: moveu mensagem {mensagem_id} para a lixeira")
        return envelope(con, {"id": mensagem_id, "estado": "na_lixeira"}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/regra-lixo")
async def regra_de_lixo(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """O dono diz "sempre que vier deste remetente (`tipo`: remetente) ou deste domínio (`tipo`: dominio), é lixo": acrescenta a regra em `email.regras_lixo`.
    Só grava a regra: as mensagens novas vão para a lixeira (nunca apaga de vez) nas rodadas seguintes, e as travas (VIP, pessoa, respondido, palavra protegida)
    continuam valendo. Idempotente. A auditoria leva só o id da mensagem e o tipo, nunca o endereço."""
    corpo = _corpo(await _json(request))
    tipo = corpo.get("tipo")
    if tipo not in ("remetente", "dominio"):
        raise erro(400, "requisicao_invalida", "tipo deve ser remetente ou dominio")
    con = _con(request)
    try:
        m = con.execute("select remetente from email_msg where id=?", (mensagem_id,)).fetchone()
        if m is None:
            raise erro(404, "nao_encontrado", "mensagem não existe")
        a = endereco(m["remetente"])
        if a is None:
            raise erro(409, "conflito", "a mensagem não tem um remetente válido para virar regra")
        regra = a if tipo == "remetente" else "@" + a.split("@", 1)[1]
        with transacao(con):
            try:
                _, nova = fn.acrescentar_regra_lixo(con, regra)
            except fn.ErroFonte as e:
                raise _traduzir(e) from None
            if nova:
                _audit(con, ident.login, f"correio: regra de lixo ({tipo}) a partir da mensagem {mensagem_id}")
        return envelope(con, {"id": mensagem_id, "regra": regra}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/nao-e-lixo")
async def nao_e_lixo(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """O dono diz que o "lixo sugerido" não é lixo: marca `restaurada` (a Gabi nunca a move). Não toca no Gmail. Idempotente."""
    await _json(request)
    con = _con(request)
    try:
        m = _mensagem(con, mensagem_id)
        if m["estado"] == "restaurada":
            return envelope(con, {"id": mensagem_id, "estado": "restaurada"}, agora=_agora(request))
        if m["estado"] != "classificada" or m["classe"] != "lixo":
            raise erro(409, "conflito", "a mensagem não está entre o lixo sugerido")
        agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
        with transacao(con):
            con.execute("update email_msg set estado='restaurada', atualizado_em=? where id=? and estado='classificada'", (agora, mensagem_id))
            _audit(con, ident.login, f"correio: marcou mensagem {mensagem_id} como não é lixo")
        return envelope(con, {"id": mensagem_id, "estado": "restaurada"}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/dispensar")
async def dispensar(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Marca um e-mail emergencial, importante ou normal como tratado: sai das listas e do resumo da manhã e fecha o alerta da conversa. Não vai para a lixeira nem
    mexe no Gmail. Idempotente."""
    await _json(request)
    con = _con(request)
    try:
        m = _mensagem(con, mensagem_id)
        if m["dispensada_em"]:
            return envelope(con, {"id": mensagem_id, "dispensada": True}, agora=_agora(request))
        if m["estado"] not in ("classificada", "alertada") or m["classe"] not in ("emergencial", "importante", "normal"):
            raise erro(409, "conflito", "só dá para dispensar e-mail emergencial, importante ou normal que está na fila")
        agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
        with transacao(con):
            con.execute("update email_msg set dispensada_em=? where id=? and dispensada_em is null", (agora, mensagem_id))
            fechar_alerta(con, m["thread_id"] or m["externo_id"], agora)
            _audit(con, ident.login, f"correio: dispensou mensagem {mensagem_id}")
        return envelope(con, {"id": mensagem_id, "dispensada": True}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/desfazer-dispensa")
async def desfazer_dispensa(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Volta a mensagem dispensada para as listas (o alerta já fechado não reabre). Idempotente."""
    await _json(request)
    con = _con(request)
    try:
        m = _mensagem(con, mensagem_id)
        if m["dispensada_em"]:
            with transacao(con):
                con.execute("update email_msg set dispensada_em=null where id=?", (mensagem_id,))
                _audit(con, ident.login, f"correio: desfez a dispensa da mensagem {mensagem_id}")
        return envelope(con, {"id": mensagem_id, "dispensada": False}, agora=_agora(request))
    finally:
        con.close()


@router.post("/mensagens/{mensagem_id}/restaurar")
async def restaurar(mensagem_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Tira da lixeira (pela ponte) e marca `restaurada`: a Gabi nunca a move de novo. Idempotente. 503 `fonte_indisponivel` se a ponte ou o Gmail não confirmar."""
    await _json(request)
    con = _con(request)
    try:
        m = con.execute("select m.id, m.externo_id, m.thread_id, m.estado, f.conta, f.provedor from email_msg m join email_fonte f on f.id=m.fonte_id where m.id=?", (mensagem_id,)).fetchone()
        if m is None:
            raise erro(404, "nao_encontrado", "mensagem não existe")
        if m["estado"] == "restaurada":
            return envelope(con, {"id": mensagem_id, "estado": "restaurada"}, agora=_agora(request))
        if m["estado"] != "na_lixeira":
            raise erro(409, "conflito", "a mensagem não está na lixeira")
        fabrica = request.app.state.fontes.get(_FONTE_EMAIL[m["provedor"]])
        fonte = fabrica() if fabrica else None
        if fonte is None:
            raise erro(503, "fonte_indisponivel", "o e-mail do Google não está configurado")
        try:
            resultado = await asyncio.to_thread(fonte.restaurar, m["conta"], [m["externo_id"]])  # rede bloqueante: fora do laço da API
        except (ErroGoogleOAuth, ErroGraphNess) as e:
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
