"""Painel da escuta (/api/v1/escuta): fila de remetentes, grupos e parâmetros. Só o boss.
A API NÃO toca o spool: ignorar/bloquear só anulam ponteiros no banco; o timer da escuta apaga os arquivos órfãos.
Número, nome e palavras de risco nunca vão para log; a auditoria de parâmetros leva só os nomes das chaves.. Consome: escuta.remetentes, escuta.caixa."""
import datetime as dt
import json

from fastapi import APIRouter, Depends, Request, Response

from gabi.cobrar.cadastro import dados
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.escuta import remetentes as rem
from gabi.contatos.telefone import normalizar_telefone
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/escuta", dependencies=[Depends(exigir("boss"))])

PADROES = {"modo": "registro", "palavras_risco": [], "horas_sem_receber": 12, "anexo_max_mb": 25}
CHAVES = {k: f"escuta.{k}" for k in PADROES}


def _numero(bruto: str, request: Request | None = None) -> str:
    """Telefone normalizado; ou o id CRU (LID etc.) quando ele já existe em escuta_remetente (I4). Senão 404."""
    n = normalizar_telefone(bruto.strip())
    if n is not None:
        return n
    if request is not None and bruto.strip():
        con = _con(request)
        try:
            if con.execute("select 1 from escuta_remetente where numero=?", (bruto.strip(),)).fetchone():
                return bruto.strip()
        finally:
            con.close()
    raise erro(404, "nao_encontrado", "número inválido")


def _inteiro(v, nome: str, minimo: int, maximo: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not minimo <= v <= maximo:
        raise erro(400, "requisicao_invalida", f"{nome} deve ser um inteiro de {minimo} a {maximo}")
    return v


def _validar(corpo: dict) -> dict:
    if not corpo:
        raise erro(400, "requisicao_invalida", "envie ao menos um parâmetro")
    extra = set(corpo) - set(PADROES)
    if extra:
        raise erro(400, "requisicao_invalida", f"parâmetros desconhecidos: {sorted(extra)}")
    saida = {}
    for k, v in corpo.items():
        if k == "modo":
            if v not in ("registro", "ativo"):
                raise erro(400, "requisicao_invalida", "modo deve ser 'registro' ou 'ativo'")
        elif k == "palavras_risco":
            if (not isinstance(v, list) or len(v) > 200 or not all(isinstance(p, str) and p.strip() and len(p) <= 60 for p in v)):
                raise erro(400, "requisicao_invalida", "palavras_risco deve ser uma lista de até 200 textos não vazios de até 60 caracteres")
            v = [p.strip() for p in v]
        elif k == "horas_sem_receber":
            _inteiro(v, k, 1, 168)
        elif k == "anexo_max_mb":
            _inteiro(v, k, 1, 100)
        saida[k] = v
    return saida


def _parametros(con) -> dict:
    saida = {}
    for k, chave in CHAVES.items():
        r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
        try:
            v = json.loads(r[0]) if r else PADROES[k]
        except (ValueError, TypeError):
            v = PADROES[k]
        saida[k] = v
    return saida


def _aprovados(con) -> list[dict]:
    saida = []
    for p in con.execute("select id, nome, dados from pessoa where excluido_em is null order by nome, id"):
        d = dados(p)
        if d.get("escuta_aprovada") is not True:
            continue
        canais = [c for c in (d.get("canais") or []) if isinstance(c, str) and c.startswith("whatsapp:")]
        numero = next((n for c in canais if (n := normalizar_telefone(c[9:]))), None) or next((c[9:] for c in canais if c[9:]), None)
        saida.append({"pessoa_id": p["id"], "nome": p["nome"], "numero": numero, "papel": d.get("papel_escuta")})
    return saida


@router.get("/remetentes")
def remetentes(request: Request):
    """Fila de remetentes novos (pendentes) e a lista de aprovados da escuta."""
    con = _con(request)
    try:
        return envelope(con, {"fila": rem.fila(con), "aprovados": _aprovados(con)}, agora=_agora(request))
    finally:
        con.close()


@router.post("/remetentes/{numero}/aprovar")
async def aprovar(numero: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova um remetente com um papel (familia, prestador ou cobranca); nome é opcional."""
    corpo = _corpo(await _json(request))
    papel, nome = corpo.get("papel"), corpo.get("nome")
    if papel not in rem.PAPEIS:
        raise erro(400, "requisicao_invalida", f"papel deve ser um de {list(rem.PAPEIS)}")
    if nome is not None and (not isinstance(nome, str) or len(nome) > 120):
        raise erro(400, "requisicao_invalida", "nome deve ser texto de até 120 caracteres")
    n = _numero(numero, request)
    if normalizar_telefone(n) is None and not (nome or "").strip():
        raise erro(400, "requisicao_invalida", "remetente sem telefone (id do WhatsApp): informe o nome para aprovar")
    con = _con(request)
    try:
        pid = rem.aprovar(con, n, papel, (nome or "").strip() or None, ident.login)
        return envelope(con, {"numero": n, "pessoa_id": pid, "papel": papel}, agora=_agora(request))
    finally:
        con.close()


async def _descartar(numero: str, request: Request, ident: Identidade, fn, estado: str):
    await _json(request)
    n = _numero(numero, request)
    con = _con(request)
    try:
        fn(con, n, ident.login, None)  # spool=None: a API não apaga arquivo
        return envelope(con, {"numero": n, "estado": estado}, agora=_agora(request))
    finally:
        con.close()


@router.post("/remetentes/{numero}/ignorar")
async def ignorar(numero: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Ignora um remetente: some da fila e as mensagens retidas dele perdem o texto."""
    return await _descartar(numero, request, ident, rem.ignorar, "ignorado")


@router.post("/remetentes/{numero}/bloquear")
async def bloquear(numero: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Bloqueia um remetente: nada novo dele é guardado."""
    return await _descartar(numero, request, ident, rem.bloquear, "bloqueado")


@router.get("/grupos")
def grupos(request: Request):
    """Grupos de WhatsApp vistos pela escuta e se já foram aprovados."""
    con = _con(request)
    try:
        itens = [{"id_grupo": r["id_grupo"], "nome": r["nome"], "aprovado": bool(r["aprovado"]), "comprovantes": bool(r["comprovantes"])}
                 for r in con.execute("select id_grupo, nome, aprovado, comprovantes from escuta_grupo order by nome, id_grupo")]
        return envelope(con, {"grupos": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/grupos/{id_grupo}/aprovar")
async def aprovar_grupo(id_grupo: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova um grupo de WhatsApp para a escuta (404 se o grupo nunca foi visto)."""
    await _json(request)
    con = _con(request)
    try:
        with transacao(con):
            if con.execute("select 1 from escuta_grupo where id_grupo=?", (id_grupo,)).fetchone() is None:
                raise erro(404, "nao_encontrado", "grupo não existe")
            con.execute("update escuta_grupo set aprovado=1 where id_grupo=?", (id_grupo,))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')",
                        (dt.datetime.now(dt.timezone.utc).isoformat(), ident.login, f"escuta: aprovou grupo {id_grupo}"))
        return envelope(con, {"id_grupo": id_grupo, "aprovado": True}, agora=_agora(request))
    finally:
        con.close()


@router.post("/grupos/{id_grupo}/comprovantes")
async def grupo_comprovantes(id_grupo: str, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Define a caixa de comprovantes (CP1 B): só anexos encaminhados a este grupo vão ao Paperless. Um grupo por vez; troca a anterior.
    404 se o grupo nunca foi visto; 409 se não está aprovado."""
    await _json(request)
    con = _con(request)
    try:
        with transacao(con):
            g = con.execute("select aprovado from escuta_grupo where id_grupo=?", (id_grupo,)).fetchone()
            if g is None:
                raise erro(404, "nao_encontrado", "grupo não existe")
            if not g["aprovado"]:
                raise erro(409, "grupo_nao_aprovado", "aprove o grupo antes de torná-lo caixa de comprovantes")
            con.execute("update escuta_grupo set comprovantes=0 where comprovantes=1")
            con.execute("update escuta_grupo set comprovantes=1 where id_grupo=?", (id_grupo,))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')",
                        (dt.datetime.now(dt.timezone.utc).isoformat(), ident.login, f"escuta: caixa de comprovantes = grupo {id_grupo}"))
        return envelope(con, {"id_grupo": id_grupo, "comprovantes": True}, agora=_agora(request))
    finally:
        con.close()


@router.get("/parametros")
def parametros(request: Request):
    """Parâmetros da escuta: modo, palavras de risco, horas sem receber e tamanho máximo de anexo (padrões se não definidos)."""
    con = _con(request)
    try:
        return envelope(con, _parametros(con), agora=_agora(request))
    finally:
        con.close()


@router.put("/parametros")
async def gravar_parametros(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Grava parâmetros da escuta (só os enviados); valida modo, lista de palavras e faixas, e audita só os nomes."""
    novos = _validar(_corpo(await _json(request)))
    con = _con(request)
    try:
        with transacao(con):
            for k, v in novos.items():
                con.execute("insert into parametro(chave, valor) values (?,?) on conflict(chave) do update set valor=excluded.valor",
                            (CHAVES[k], json.dumps(v, ensure_ascii=False)))
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')",
                        (dt.datetime.now(dt.timezone.utc).isoformat(), ident.login, "escuta: alterou parâmetros " + ", ".join(sorted(CHAVES[k] for k in novos))))
        return envelope(con, _parametros(con), agora=_agora(request))
    finally:
        con.close()
