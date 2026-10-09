"""Rotas /api/v1 da Fase 3: Hoje, Frentes, Agenda, Mensagens e Tarefas. Lê só de tabelas prontas; concluir tarefa age NA ORIGEM (R2: sem envio/exclusão).
Consome: trabalho.*, envelope, fontes (`concluir_tarefa` em app.state.fontes)."""
from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.identidade import exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _data, _json, erro
from gabi.trabalho import email, frentes, hoje as modulo_hoje

router = APIRouter(prefix="/api/v1", dependencies=[Depends(exigir("boss"))])


def _filtro(f: str) -> str:
    if f == "all" or f.startswith("t-") and f[2:].isdigit() or f.replace("-", "").replace("_", "").isalnum():
        return f
    raise erro(400, "requisicao_invalida", "filtro inválido")


@router.get("/hoje")
def hoje(request: Request, filtro: str = "all"):
    """O dia do Ricardo: prioridades, agenda, e-mails que importam e dinheiro (filtro all, empresa ou t-<frente>)."""
    con = _con(request)
    try:
        return envelope(con, modulo_hoje.hoje(con, _agora(request), _filtro(filtro)), agora=_agora(request))
    finally:
        con.close()


@router.get("/frentes")
def listar_frentes(request: Request):
    """Frentes de trabalho com a contagem de itens confirmados."""
    con = _con(request)
    try:
        itens = [dict(r) | {"confirmados": len(frentes.itens(con, r["id"]))} for r in con.execute("select id, nome, tipo, empresa_id, pai_id from frente order by nome")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.get("/frentes/{frente_id}")
def detalhe_frente(request: Request, frente_id: int):
    """Uma frente: e-mails confirmados e os sugeridos que aguardam confirmação."""
    con = _con(request)
    try:
        f = con.execute("select id, nome, tipo, empresa_id, pai_id from frente where id=?", (frente_id,)).fetchone()
        if f is None:
            raise erro(404, "nao_encontrado", "frente não existe")
        ids = frentes.itens(con, frente_id)
        mails = [dict(r) for r in con.execute(f"select id, remetente, assunto, recebido_em, motivo from item_email where id in ({','.join('?' * len(ids)) or 'null'}) order by recebido_em desc", ids)]
        sugeridos = [dict(r) for r in con.execute(
            "select i.id, i.remetente, i.assunto, f.origem as motivo from item_frente f join item_email i on i.id=f.ref_id where f.frente_id=? and f.estado='sugerido'", (frente_id,))]
        return envelope(con, {"frente": dict(f), "emails": mails, "sugeridos": sugeridos}, agora=_agora(request))
    finally:
        con.close()


@router.post("/frentes")
async def criar_frente(request: Request):
    """Abre uma frente (nome, tipo, empresa e regra vêm do Ricardo)."""
    corpo = _corpo(await _json(request))
    con = _con(request)
    try:
        try:
            fid = frentes.abrir_frente(con, corpo.get("nome") or "", corpo.get("tipo") or "", corpo.get("empresa_id"), corpo.get("regra"))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e)) from None
        if not corpo.get("nome"):
            raise erro(400, "requisicao_invalida", "informe o nome")
        return envelope(con, {"id": fid}, agora=_agora(request))
    finally:
        con.close()


@router.post("/frentes/{frente_id}/itens/{item_id}/confirmar")
def confirmar_item(request: Request, frente_id: int, item_id: int):
    """Confirma que um e-mail entra na frente (só o Ricardo decide)."""
    con = _con(request)
    try:
        frentes.confirmar(con, frente_id, item_id, por="boss")
        return envelope(con, {"ok": True}, agora=_agora(request))
    finally:
        con.close()


@router.get("/agenda")
def agenda(request: Request, de: str | None = None, ate: str | None = None):
    """Eventos do período e conflitos com sugestão de horário (proposta, não envia nada)."""
    con = _con(request)
    try:
        d1, d2 = _data(de, "de"), _data(ate, "ate")
        d1 = d1 or _agora(request).date()
        d2 = d2 or d1
        eventos = [dict(r) for r in con.execute("select id, inicio, fim, titulo, link_reuniao from evento where date(inicio)>=? and date(inicio)<=? order by inicio",
                                               (d1.isoformat(), d2.isoformat()))]
        conflitos = [{"evento_a": c.evento_a, "evento_b": c.evento_b, "sugestao_inicio": c.sugestao_inicio}
                     for c in email.conflitos(con, f"{d1.isoformat()}T00:00:00", f"{d2.isoformat()}T23:59:59")]
        return envelope(con, {"eventos": eventos, "conflitos": conflitos}, agora=_agora(request))
    finally:
        con.close()


@router.get("/mensagens")
def mensagens(request: Request, limite: int = 50):
    """E-mails recentes (cabeçalho e trecho) e os ids que o expurgo sugere (nada é apagado aqui)."""
    con = _con(request)
    try:
        itens = [dict(r) for r in con.execute(
            "select i.id, i.remetente, i.assunto, i.recebido_em, i.relevante, i.motivo, i.estado, c.endereco as caixa from item_email i "
            "join caixa_email c on c.id=i.caixa_id order by i.recebido_em desc limit ?", (min(max(limite, 1), 200),))]
        return envelope(con, {"itens": itens, "expurgo_sugerido": email.expurgo_sugerido(con)}, agora=_agora(request))
    finally:
        con.close()


@router.get("/tarefas")
def tarefas(request: Request):
    """Tarefas abertas e concluídas, de todas as origens."""
    con = _con(request)
    try:
        itens = [dict(r) for r in con.execute("select id, origem, titulo, prazo, estado from tarefa order by estado, prazo is null, prazo")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/tarefas/{tarefa_id}/concluir")
def concluir(request: Request, tarefa_id: int):
    """Conclui a tarefa NA ORIGEM (Graph ou Google) e só então marca aqui."""
    con = _con(request)
    try:
        t = con.execute("select id, origem, externo_id, estado from tarefa where id=?", (tarefa_id,)).fetchone()
        if t is None:
            raise erro(404, "nao_encontrado", "tarefa não existe")
        if t["estado"] == "concluida":
            return envelope(con, {"ok": True}, agora=_agora(request))
        fn = request.app.state.fontes.get("concluir_tarefa")
        fn = fn() if fn else None
        if fn is None:
            raise erro(503, "fonte_indisponivel", "a origem da tarefa não está configurada")
        fn(t["origem"], t["externo_id"])                       # age na origem primeiro; só então marca aqui
        con.execute("update tarefa set estado='concluida' where id=?", (tarefa_id,))
        return envelope(con, {"ok": True}, agora=_agora(request))
    finally:
        con.close()
