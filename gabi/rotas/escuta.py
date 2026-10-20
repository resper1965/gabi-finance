"""Painel da escuta (/api/v1/escuta): fila de remetentes, grupos e parâmetros. Só o boss.
A API NÃO toca o spool: ignorar/bloquear só anulam ponteiros no banco; o timer da escuta apaga os arquivos órfãos.
Número, nome e palavras de risco nunca vão para log; a auditoria de parâmetros leva só os nomes das chaves. Contatos do Google: só nome, telefone e e-mail, lidos pela ponte do serviço de fontes (a API não tem rede). Consome: escuta.remetentes, escuta.caixa, escuta.contatos."""
import datetime as dt
import json

from fastapi import APIRouter, Depends, Request, Response

from gabi.cobrar.cadastro import dados
from gabi.db import transacao
from gabi.envelope import envelope
from gabi.escuta import contatos as ct
from gabi.escuta import contatos_gravar as cg
from gabi.escuta import contatos_propostas as cp
from gabi.escuta import remetentes as rem
from gabi.escuta.caixa import normalizar_telefone
from gabi.fontes.google_contatos import ErroGoogleContatos
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.fontes.roteador import roteador_contatos
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


# ---------------- contatos do Google (só nome, telefone e e-mail) ----------------
MAX_TRAZER = 100


def _audit(con, quem: str, o_que: str) -> None:
    con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'escuta')", (dt.datetime.now(dt.timezone.utc).isoformat(), quem, o_que))


def _numeros_de_pessoas(con) -> set[str]:
    saida = set()
    for p in con.execute("select dados from pessoa where excluido_em is null"):
        for c in dados(p).get("canais") or []:
            if isinstance(c, str) and c.startswith("whatsapp:") and (n := normalizar_telefone(c[9:])):
                saida.add(n)
    return saida


@router.post("/contatos/sincronizar")
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
        _audit(con, ident.login, f"escuta: sincronizou contatos (total {r['total']}, inválidos {r['invalidos']}, contas com erro {len(falhas)})")
        return envelope(con, r, agora=_agora(request))
    finally:
        con.close()


@router.get("/contatos")
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


@router.get("/contatos/so-na-ness.csv", response_class=Response,
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


@router.post("/contatos/trazer")
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
                pid, d, estado = rem.garantir_pessoa(con, n, nomes[n])
                if estado == "existente":
                    continue
                if estado == "reativada":  # trazer nunca aprova: o que a pessoa excluída tinha de aprovação não volta
                    d.pop("escuta_aprovada", None)
                    d.pop("pode_pedir", None)
                con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), pid))
                criadas += 1
            ignoradas = len(tels) - criadas
            _audit(con, ident.login, f"escuta: trouxe {criadas} contato(s) como pessoa ({ignoradas} ignorado(s))")
        return envelope(con, {"criadas": criadas, "ignoradas": ignoradas}, agora=_agora(request))
    finally:
        con.close()


ESTADOS_PROPOSTA = ("pendente", "aprovada", "recusada", "aplicada", "falhou")


def _agora_utc(request: Request) -> str:
    return _agora(request).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/contatos/propostas")
def listar_propostas(request: Request, estado: str = "pendente", ident: Identidade = Depends(exigir("boss"))):
    """Lista as propostas de criar/corrigir contato da ness (padrão: pendentes) com nome e telefone, e diz se a escrita no Graph está ligada."""
    if estado not in ESTADOS_PROPOSTA:
        raise erro(400, "requisicao_invalida", f"estado deve ser um de: {', '.join(ESTADOS_PROPOSTA)}")
    con = _con(request)
    try:
        itens = cp.listar(con, estado)
        escrita = "ligado" if cg.escrita_ligada(con) else "desligado"
        return envelope(con, {"itens": itens, "escrita": escrita}, agora=_agora(request))
    finally:
        con.close()


@router.post("/contatos/propostas/aprovar-correcoes")
def aprovar_correcoes_propostas(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova de uma vez todas as propostas pendentes do tipo corrigir (telefone inválido); devolve quantas."""
    con = _con(request)
    try:
        n = cp.aprovar_correcoes(con, ident.login, _agora_utc(request),
                                 auditar=lambda n: _audit(con, ident.login, f"escuta: aprovou {n} correção(ões) de contato"))
        return envelope(con, {"aprovadas": n}, agora=_agora(request))
    finally:
        con.close()


@router.post("/contatos/propostas/{proposta_id}/decisao")
async def decidir_proposta(proposta_id: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Aprova ou recusa uma proposta pendente de contato (corpo {"estado": "aprovada"|"recusada"}); 404 se não existe, 409 se já foi decidida."""
    corpo = _corpo(await _json(request))
    estado = corpo.get("estado")
    if estado not in cp.ESTADOS_DECISAO:
        raise erro(400, "requisicao_invalida", "estado deve ser aprovada ou recusada")
    con = _con(request)
    try:
        try:
            cp.decidir(con, proposta_id, estado, ident.login, _agora_utc(request),
                       auditar=lambda: _audit(con, ident.login, f"escuta: contato proposta {proposta_id} → {estado}"))
        except cp.ErroProposta as e:
            if e.nao_encontrado:
                raise erro(404, "nao_encontrado", str(e))
            raise erro(409 if e.conflito else 400, "conflito" if e.conflito else "requisicao_invalida", str(e))
        return envelope(con, {"id": proposta_id, "estado": estado}, agora=_agora(request))
    finally:
        con.close()


@router.delete("/contatos")
def apagar_contatos(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Revoga: apaga todos os contatos do Google guardados (as pessoas já criadas ficam)."""
    con = _con(request)
    try:
        with transacao(con):
            n = con.execute("delete from contato_google").rowcount
            con.execute("delete from contato_google_email")  # revogar leva também os e-mails dos contatos (migração 0070)
            _audit(con, ident.login, f"escuta: apagou contatos do Google ({n} linha(s))")
        return envelope(con, {"apagados": n}, agora=_agora(request))
    finally:
        con.close()
