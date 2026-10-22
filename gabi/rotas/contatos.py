"""Contatos (/api/v1/contatos): lista, sincronização, CSV, trazer como pessoa e a fila de propostas de escrita no Graph da ness. Só o boss.
Contatos do Google/Graph: só nome, telefone e e-mail, lidos pela ponte do serviço de fontes (a API não tem rede). Veio de rotas/escuta.py (ADR-023).
Consome: contatos.contatos, contatos.contatos_propostas, contatos.contatos_gravar, contatos.pessoas."""
import datetime as dt
import json

from fastapi import APIRouter, Depends, Request, Response

from gabi.cobrar.cadastro import dados
from gabi.contatos import contatos as ct
from gabi.contatos import contatos_gravar as cg
from gabi.contatos import contatos_propostas as cp
from gabi.contatos.pessoas import garantir_pessoa
from gabi.contatos.telefone import normalizar_telefone
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.fontes.roteador import roteador_contatos
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/contatos", dependencies=[Depends(exigir("boss"))])

# ---------------- contatos do Google (só nome, telefone e e-mail) ----------------
MAX_TRAZER = 100


def _audit(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'contatos')", (dt.datetime.now(dt.timezone.utc).isoformat(), quem, o_que))


def _numeros_de_pessoas(con) -> set[str]:
    saida = set()
    for p in con.execute("select dados from pessoa where excluido_em is null"):
        for c in dados(p).get("canais") or []:
            if isinstance(c, str) and c.startswith("whatsapp:") and (n := normalizar_telefone(c[9:])):
                saida.add(n)
    return saida


@router.post("/sincronizar")
def sincronizar_contatos(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Lê os contatos das contas do Google (pela ponte) e grava nome, telefone e e-mail; devolve contagens e o erro de cada conta que falhou.
    200 se ao menos uma conta sincronizou; 503 `fonte_indisponivel` se nenhuma sincronizou ou a ponte está fora do ar."""
    fontes = request.app.state.fontes
    fabrica, fabrica_graph = fontes.get("google_contatos"), fontes.get("graph_ness")
    google, graph = (fabrica() if fabrica else None), (fabrica_graph() if fabrica_graph else None)
    if google is None and graph is None:
        raise erro(503, "fonte_indisponivel", "os contatos do Google não estão configurados")
    # a conta do Graph (ness) vai ao Graph; as demais ao Google. A lista de contas do Graph vem da ponte (rede só no serviço de fontes)
    try:
        listar = roteador_contatos(google.listar if google else None, graph.contatos if graph else None, graph.contas() if graph else [])
    except ErroGraphNess as e:
        raise erro(503, "fonte_indisponivel", str(e)) from None
    con = _con(request)
    try:
        r = ct.sincronizar(con, ct.contas_contatos(con), listar)
        falhas = {k: v["erro"] for k, v in r["contas"].items() if "erro" in v}
        if r["contas"] and len(falhas) == len(r["contas"]):  # nenhuma conta sincronizou (ou a ponte está fora do ar)
            raise erro(503, "fonte_indisponivel", "nenhuma conta sincronizou: " + "; ".join(f"{k}: {m}" for k, m in falhas.items()))
        _audit(con, ident.login, f"contatos: sincronizou contatos (total {r['total']}, inválidos {r['invalidos']}, contas com erro {len(falhas)})")
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.get("")
def listar_contatos(request: Request, busca: str = "", limite: int = 50, offset: int = 0):
    """Contatos (um por telefone; o nome do Gmail vence), com as contas em que existem e se o número já é uma pessoa. Paginado."""
    limite, offset = min(max(limite, 1), 200), max(offset, 0)
    con = _con(request)
    try:
        itens, q = ct.listar_unicos(con), busca.strip().casefold()
        if q:
            digitos = "".join(ch for ch in q if ch.isdigit())
            itens = [i for i in itens if q in (i["nome"] or "").casefold() or (digitos and digitos in i["telefone"])]
        pessoas = _numeros_de_pessoas(con)
        pagina = [{**i, "ja_e_pessoa": i["telefone"] in pessoas} for i in itens[offset:offset + limite]]
        return envelope(con, {"itens": pagina, "total": len(itens), "limite": limite, "offset": offset}, agora=_agora(request))
    finally:
        con.close()


@router.get("/so-na-ness.csv", response_class=Response,
            responses={200: {"description": "CSV do importador do Google (Name, Phone 1 - Value)", "content": {"text/csv": {"schema": {"type": "string"}}}}})
def contatos_so_na_ness(request: Request):
    """CSV (importador do Google: Name, Phone 1 - Value) dos contatos que estão na conta de origem e não na de destino."""
    con = _con(request)
    try:
        texto = ct.csv_google(ct.so_na(con, ct.conta_origem(con), ct.conta_destino(con)))
    finally:
        con.close()
    return Response(texto, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="contatos-so-na-ness.csv"', "Cache-Control": "no-store"})


@router.post("/trazer")
async def trazer_contatos(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria uma `pessoa` (canal whatsapp, nome do contato) para cada telefone escolhido que ainda não é pessoa. NUNCA aprova a escuta nem dá pode_pedir."""
    corpo = _corpo(await _json(request))
    tels = corpo.get("telefones")
    if not isinstance(tels, list) or not tels or len(tels) > MAX_TRAZER or not all(isinstance(t, str) for t in tels):
        raise erro(400, "requisicao_invalida", f"telefones deve ser uma lista de 1 a {MAX_TRAZER} textos")
    con = _con(request)
    try:
        criadas = 0
        with transacao(con):
            existentes = _numeros_de_pessoas(con)
            vistos: set[str] = set()
            nomes = {i["telefone"]: i["nome"] for i in ct.listar_unicos(con)}
            for bruto in tels:
                n = normalizar_telefone(bruto)
                if n is None or n not in nomes or n in existentes or n in vistos:
                    continue
                vistos.add(n)
                pid, d, estado = garantir_pessoa(con, n, nomes[n])
                if estado == "existente":
                    continue
                if estado == "reativada":  # trazer nunca aprova: o que a pessoa excluída tinha de aprovação não volta
                    d.pop("escuta_aprovada", None)
                    d.pop("pode_pedir", None)
                con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), pid))
                criadas += 1
            ignoradas = len(tels) - criadas
            _audit(con, ident.login, f"contatos: trouxe {criadas} contato(s) como pessoa ({ignoradas} ignorado(s))")
        return envelope(con, {"criadas": criadas, "ignoradas": ignoradas}, agora=_agora(request))
    finally:
        con.close()


ESTADOS_PROPOSTA = ("pendente", "aprovada", "recusada", "aplicada", "falhou")


def _agora_utc(request: Request) -> str:
    return _agora(request).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/propostas")
def listar_propostas(request: Request, estado: str = "pendente", ident: Identidade = Depends(exigir("boss"))):
    """Lista as propostas de contato da ness (criar, corrigir, corrigir nome, adicionar e-mail, apagar telefone, apagar contato) (padrão: pendentes) com nome, telefone e e-mails (email_depois, separados por ;), e diz se a escrita no Graph está ligada."""
    if estado not in ESTADOS_PROPOSTA:
        raise erro(400, "requisicao_invalida", f"estado deve ser um de: {', '.join(ESTADOS_PROPOSTA)}")
    con = _con(request)
    try:
        itens = cp.listar(con, estado)
        escrita = "ligado" if cg.escrita_ligada(con) else "desligado"
        return envelope(con, {"itens": itens, "escrita": escrita}, agora=_agora(request))
    finally:
        con.close()


@router.post("/propostas/aprovar-correcoes")
async def aprovar_correcoes_propostas(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova as correções (telefone e nome) e os adicionar e-mail pendentes cujos ids vieram no corpo ({"ids": [int, ...]}, as que o painel mostra); criar, apagar e não pendentes ficam (só um a um); devolve quantas."""
    corpo = _corpo(await _json(request))
    try:
        ids = cp.ids_validos(corpo.get("ids"))
    except cp.ErroProposta as e:
        raise erro(400, "requisicao_invalida", str(e))
    con = _con(request)
    try:
        n = cp.aprovar_correcoes(con, ident.login, _agora_utc(request), ids,
                                 auditar=lambda n: _audit(con, ident.login, f"contatos: aprovou {n} correção(ões) de contato"))
        return envelope(con, {"aprovadas": n}, agora=_agora(request))
    finally:
        con.close()


@router.post("/propostas/{proposta_id}/decisao")
async def decidir_proposta(proposta_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova ou recusa uma proposta pendente de contato, ou recusa uma já aprovada (corpo {"estado": "aprovada"|"recusada"}); 404 se não existe, 409 se já foi decidida."""
    corpo = _corpo(await _json(request))
    estado = corpo.get("estado")
    if estado not in cp.ESTADOS_DECISAO:
        raise erro(400, "requisicao_invalida", "estado deve ser aprovada ou recusada")
    con = _con(request)
    try:
        try:
            cp.decidir(con, proposta_id, estado, ident.login, _agora_utc(request),
                       auditar=lambda: _audit(con, ident.login, f"contatos: contato proposta {proposta_id} → {estado}"))
        except cp.ErroProposta as e:
            if e.nao_encontrado:
                raise erro(404, "nao_encontrado", str(e))
            raise erro(409 if e.conflito else 400, "conflito" if e.conflito else "requisicao_invalida", str(e))
        return envelope(con, {"id": proposta_id, "estado": estado}, agora=_agora(request))
    finally:
        con.close()


@router.delete("")
def apagar_contatos(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Revoga: apaga todos os contatos do Google guardados (as pessoas já criadas ficam)."""
    con = _con(request)
    try:
        with transacao(con):
            n = con.execute("delete from contato_google").rowcount
            con.execute("delete from contato_google_email")  # revogar leva também os e-mails dos contatos (migração 0070)
            _audit(con, ident.login, f"contatos: apagou contatos do Google ({n} linha(s))")
        return envelope(con, {"apagados": n}, agora=_agora(request))
    finally:
        con.close()
