"""Rotas /api/v1/familia: exames (T4.2). A saúde vive em arquivo próprio e criptografado (ADR-014), nunca no banco principal.
Quem vê o quê vem da matriz_acesso ('saúde'): total = todos; parcial = só a própria pessoa; nenhum = 403. Todo acesso entra no log do cofre.
Enviar/confirmar (também em lote)/rejeitar/reprocessar laudo e apelidos de marcador: só boss com grau total; a contagem "a confirmar" só pede nível boss. Consome: familia.{saude,exames}, identidade, fontes (Paperless, pela ponte)."""
import datetime as dt
import threading
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from gabi.dinheiro.modelo import Orcamento, orcamento_do_banco
from gabi.envelope import envelope
from gabi.familia import exames, marcadores as apelidos
from gabi.familia.extrair import extrair
from gabi.familia.rodada_exames import reprocessar_documentos
from gabi.familia.saude import abrir_saude, historico, marcadores, pode_ver, resumo_para_consulta, serie
from gabi.identidade import Identidade, exigir, exigir_informacao, grau
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

BRT = ZoneInfo("America/Sao_Paulo")
LIMITE_REPROCESSAR = 30  # documentos por chamada (cada um pode custar uma chamada ao modelo); o resto fica em `restantes`
router = APIRouter(prefix="/api/v1/familia")
_TRAVA = threading.Lock()  # o cofre é regravado inteiro: um escritor por vez neste processo


def _cofre(request: Request):
    cfg = getattr(request.app.state, "saude", None)
    if not cfg:
        raise erro(503, "fonte_indisponivel", "o arquivo de saúde não está configurado (falta a chave)")
    return abrir_saude(*cfg)


def _grau(request: Request, ident: Identidade) -> str:
    con = _con(request)
    try:
        return grau(con, "saúde", ident.nivel)
    finally:
        con.close()


def _ver(request: Request, ident: Identidade, pessoa_id: str) -> None:
    if not pode_ver(ident, _grau(request, ident), pessoa_id):
        raise erro(403, "sem_escopo", "Você não tem acesso a isto.")


def _resp(request: Request, dados, status_envelope=None):
    con = _con(request)
    try:
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


@router.get("/pessoas")
def pessoas(request: Request, ident: Identidade = Depends(exigir_informacao("saúde"))):
    """Pessoas cujos exames o login pode ver (boss: todas; familiar: só a própria)."""
    _cofre(request)  # 503 cedo se não houver chave
    g = _grau(request, ident)
    con = _con(request)
    try:
        itens = [{"id": r["id"], "nome": r["nome"]} for r in con.execute("select id, nome from pessoa order by nome") if pode_ver(ident, g, r["id"])]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.get("/exames/{pessoa_id}")
def lista(pessoa_id: str, request: Request, ident: Identidade = Depends(exigir_informacao("saúde"))):
    """Último valor de cada marcador de exame da pessoa; o acesso fica no log de saúde."""
    _ver(request, ident, pessoa_id)
    with _TRAVA, _cofre(request) as s:
        itens = marcadores(s, pessoa_id, ident.login)
        todos = historico(s, pessoa_id)
    return _resp(request, {"pessoa_id": pessoa_id, "marcadores": itens, "historico": todos})


@router.get("/exames/{pessoa_id}/serie")
def serie_do_marcador(pessoa_id: str, marcador: str, request: Request, ident: Identidade = Depends(exigir_informacao("saúde"))):
    """Série no tempo de um marcador da pessoa, com a marca de fora da faixa de referência."""
    _ver(request, ident, pessoa_id)
    with _TRAVA, _cofre(request) as s:
        pontos = serie(s, pessoa_id, marcador, ident.login)
    return _resp(request, {"pessoa_id": pessoa_id, "marcador": marcador,
                           "pontos": [{"em": p.em.isoformat(), "valor": p.valor, "unidade": p.unidade, "fora_da_faixa": p.fora_da_faixa} for p in pontos]})


@router.get("/exames/{pessoa_id}/resumo")
def resumo(pessoa_id: str, request: Request, ident: Identidade = Depends(exigir_informacao("saúde"))):
    """Texto "resumo para a consulta" só da pessoa escolhida."""
    _ver(request, ident, pessoa_id)
    with _TRAVA, _cofre(request) as s:
        texto = resumo_para_consulta(s, pessoa_id, ident.login)
    return _resp(request, {"pessoa_id": pessoa_id, "texto": texto})


# ---- laudos: só o boss (grau total) ----
SO_BOSS = Depends(exigir_informacao("saúde", "total"))


def _doc_estado(request: Request, pids, estado: str, *, versao: int | None = None, criar: bool = False) -> None:
    """Estado do documento no `gabi.db` (só referência: nada de valor, marcador ou paciente). Chamar DEPOIS que o cofre foi salvo."""
    agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
    con = _con(request)
    try:
        for pid in pids:
            if criar:
                con.execute("insert into exame_doc(paperless_id, estado, versao, atualizado_em) values (?,?,?,?) "
                            "on conflict(paperless_id) do update set estado=excluded.estado, versao=excluded.versao, motivo=null, atualizado_em=excluded.atualizado_em",
                            (pid, estado, versao or 0, agora))
            else:
                con.execute("update exame_doc set estado=?, atualizado_em=? where paperless_id=?", (estado, agora, pid))
    finally:
        con.close()


@router.get("/laudos")
def laudos(request: Request, ident: Identidade = SO_BOSS):
    """Laudos lidos do Paperless esperando a confirmação de quem é o laudo, e os documentos que falharam com o motivo (só boss)."""
    with _TRAVA, _cofre(request) as s:
        itens = exames.laudos_pendentes(s)
    con = _con(request)
    try:
        falhos = [{"paperless_id": r["paperless_id"], "motivo": r["motivo"]} for r in con.execute("select paperless_id, motivo from exame_doc where estado='falhou' order by paperless_id")]
        return envelope(con, {"itens": itens, "falhos": falhos}, agora=_agora(request))
    finally:
        con.close()


@router.get("/laudos/contagem")
def contagem(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Quantos documentos esperam a confirmação do dono. É o ÚNICO dado de exame fora da tela de saúde: só a contagem, lida do `gabi.db` (sem chave, sem valor, sem nome)."""
    con = _con(request)
    try:
        n = con.execute("select count(*) from exame_doc where estado='extraido'").fetchone()[0]
        return envelope(con, {"a_confirmar": n}, agora=_agora(request))
    finally:
        con.close()


@router.post("/laudos", status_code=201)
async def ler_laudo(request: Request, ident: Identidade = SO_BOSS):
    """Lê o texto de um documento do Paperless e grava PROPOSTAS de marcador (não entram até confirmar de quem é o laudo)."""
    corpo = _corpo(await _json(request))
    pid = corpo.get("paperless_id")
    if not isinstance(pid, int) or isinstance(pid, bool):
        raise erro(400, "requisicao_invalida", "paperless_id deve ser um número")
    fabrica = request.app.state.fontes.get("paperless")
    paperless = fabrica() if fabrica else None
    if paperless is None:
        raise erro(503, "fonte_indisponivel", "o Paperless não está configurado")
    docs = paperless.docs(id=pid)
    if not docs:
        raise erro(404, "nao_encontrado", f"documento {pid} não existe no Paperless")
    with _TRAVA, _cofre(request) as s:
        laudo = extrair(docs[0].get("content") or "", None, Orcamento(0, 0))  # só regras: o modelo roda no timer, com orçamento e ponte
        n = exames.propor_exames(s, pid, laudo, corpo.get("pessoa_sugerida")) if laudo else 0
        versao = exames._versao_atual(s, pid)
    if n:
        _doc_estado(request, [pid], "extraido", versao=versao, criar=True)
    return _resp(request, {"paperless_id": pid, "propostas": n})


@router.post("/laudos/{paperless_id}/confirmar")
async def confirmar(paperless_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Confirma DE QUEM é o laudo (pessoa_id); só então as propostas viram exames."""
    corpo = _corpo(await _json(request))
    try:
        with _TRAVA, _cofre(request) as s:
            n = exames.confirmar_laudo(s, paperless_id, str(corpo.get("pessoa_id") or ""), ident.login)
    except ValueError as e:
        raise erro(400, "requisicao_invalida", str(e))
    if n:
        _doc_estado(request, [paperless_id], "confirmado")
    return _resp(request, {"paperless_id": paperless_id, "exames": n})


@router.post("/laudos/lote")
async def confirmar_em_lote(request: Request, ident: Identidade = SO_BOSS):
    """Confirma o dono de vários laudos de uma vez (`itens: [{paperless_id, pessoa_id}]`): todos ou nenhum."""
    corpo = _corpo(await _json(request))
    itens = corpo.get("itens")
    if not isinstance(itens, list) or not all(isinstance(i, dict) for i in itens):
        raise erro(400, "requisicao_invalida", "itens deve ser uma lista de {paperless_id, pessoa_id}")
    con = _con(request)
    try:
        pessoas = {r["id"] for r in con.execute("select id from pessoa")}
    finally:
        con.close()
    if any(i.get("pessoa_id") not in pessoas for i in itens):
        raise erro(400, "requisicao_invalida", "pessoa_id desconhecida")
    try:
        with _TRAVA, _cofre(request) as s:
            r = exames.confirmar_lote(s, itens, ident.login)
    except ValueError as e:
        raise erro(400, "requisicao_invalida", str(e))
    _doc_estado(request, [i["paperless_id"] for i in itens], "confirmado")
    return _resp(request, r)


@router.post("/laudos/{paperless_id}/rejeitar")
async def rejeitar(paperless_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Descarta as propostas de um laudo sem registrar nenhum exame."""
    with _TRAVA, _cofre(request) as s:
        n = exames.rejeitar_laudo(s, paperless_id)
    if n:
        _doc_estado(request, [paperless_id], "descartado")
    return _resp(request, {"paperless_id": paperless_id, "rejeitadas": n})


@router.post("/exames/reprocessar")
async def reprocessar(request: Request, ident: Identidade = SO_BOSS):
    """Relê no Paperless e extrai de novo (versão nova; a anterior fica). Corpo: {paperless_id} ou {pessoa_id, laboratorio?, de?, ate?} ou {todos: true}.
    Até 30 documentos por chamada; o que sobrar vem em `restantes`. Devolve só contagens."""
    corpo = _corpo(await _json(request))
    fabrica = request.app.state.fontes.get("paperless")
    paperless = fabrica() if fabrica else None
    if paperless is None:
        raise erro(503, "fonte_indisponivel", "o Paperless não está configurado")
    pid = corpo.get("paperless_id")
    if pid is not None and (not isinstance(pid, int) or isinstance(pid, bool)):
        raise erro(400, "requisicao_invalida", "paperless_id deve ser um número")
    if pid is None and corpo.get("todos") is not True and not (isinstance(corpo.get("pessoa_id"), str) and corpo["pessoa_id"]):
        raise erro(400, "requisicao_invalida", "informe paperless_id, pessoa_id (com filtros opcionais) ou todos: true")
    fabrica_modelo = request.app.state.fontes.get("modelo")
    cliente = fabrica_modelo() if fabrica_modelo else None
    banco = request.app.state.banco
    if cliente is not None:
        from gabi.escuta.__main__ import ModeloComCusto
        cliente = ModeloComCusto(cliente, banco, tarefa="exames")
    con = _con(request)
    try:
        orcamento = orcamento_do_banco(con, _agora(request).astimezone(BRT).date())
    finally:
        con.close()
    try:
        with _TRAVA, _cofre(request) as s:
            if pid is not None:
                ids = [pid]
            elif corpo.get("todos") is True:
                ids = exames.todos_os_documentos(s)
            else:
                ids = exames.documentos_do_filtro(s, corpo["pessoa_id"], corpo.get("laboratorio"), corpo.get("de"), corpo.get("ate"))
            lote = ids[:LIMITE_REPROCESSAR]
            r, versoes = reprocessar_documentos(s, paperless, cliente, orcamento, lote, ident.login)
    finally:
        if cliente is not None:
            cliente.fechar()
    _doc_versoes(request, versoes)
    return _resp(request, {**r, "restantes": len(ids) - len(lote)})


def _doc_versoes(request: Request, versoes: dict) -> None:
    """Grava a versão atual de cada documento reprocessado; o estado que já existia (confirmado, etc.) não muda."""
    agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
    con = _con(request)
    try:
        for pid, v in versoes.items():
            con.execute("insert into exame_doc(paperless_id, estado, versao, atualizado_em) values (?, 'extraido', ?, ?) "
                        "on conflict(paperless_id) do update set versao=excluded.versao, atualizado_em=excluded.atualizado_em", (pid, v, agora))
    finally:
        con.close()


@router.get("/exames/{pessoa_id}/laudos/{paperless_id}/versoes")
def versoes_do_laudo(pessoa_id: str, paperless_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Versões da extração de um documento (para comparar a atual com a anterior)."""
    with _TRAVA, _cofre(request) as s:
        vs = exames.versoes(s, paperless_id, ident.login)
        dif = exames.diferencas(s, paperless_id, vs[-2]["versao"], vs[-1]["versao"]) if len(vs) > 1 else []
    return _resp(request, {"paperless_id": paperless_id, "versoes": vs, "diferencas": dif})


# ---- mensagens de saúde sem anexo (ficam só no cofre; só boss com grau total) ----
@router.get("/mensagens")
def mensagens_de_saude(request: Request, ident: Identidade = SO_BOSS):
    """Mensagens de saúde guardadas no cofre (id, de_pessoa, recebida_em, texto, lida_em); a leitura entra no log do cofre. O texto é dado de terceiros (R14)."""
    with _TRAVA, _cofre(request) as s:
        itens = exames.mensagens(s, ident.login)
    return _resp(request, {"itens": itens})


@router.post("/mensagens/{mensagem_id}/lida")
def mensagem_lida(mensagem_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Marca a mensagem como lida, no cofre. Não apaga nada."""
    with _TRAVA, _cofre(request) as s:
        achou = exames.marcar_lida(s, mensagem_id, ident.login, _agora(request).astimezone(dt.timezone.utc).isoformat())
    if not achou:
        raise erro(404, "nao_encontrado", "mensagem não existe")
    return _resp(request, {"id": mensagem_id, "lida": True})


# ---- apelidos de marcador ----
@router.get("/marcadores/apelidos")
def listar_apelidos(request: Request, ident: Identidade = SO_BOSS):
    """Apelidos de marcador definidos e sugestões de grafias parecidas para juntar."""
    with _TRAVA, _cofre(request) as s:
        return _resp(request, {"itens": apelidos.apelidos(s), "sugestoes": apelidos.sugestoes(s)})


@router.put("/marcadores/apelidos")
async def definir_apelido(request: Request, ident: Identidade = SO_BOSS):
    """Define um apelido (`{apelido, marcador}`); vale para as próximas extrações e para `reaplicar`."""
    corpo = _corpo(await _json(request))
    try:
        with _TRAVA, _cofre(request) as s:
            apelidos.definir_apelido(s, str(corpo.get("apelido") or ""), str(corpo.get("marcador") or ""))
            itens = apelidos.apelidos(s)
    except ValueError as e:
        raise erro(400, "requisicao_invalida", str(e))
    return _resp(request, {"itens": itens})


@router.post("/marcadores/reaplicar")
def reaplicar_apelidos(request: Request, ident: Identidade = SO_BOSS):
    """Reescreve os marcadores de exames e propostas conforme os apelidos, sem chamar o modelo."""
    with _TRAVA, _cofre(request) as s:
        n = apelidos.reaplicar(s)
    return _resp(request, {"alterados": n})


# ---- edições vindas do cofre Obsidian (ficam pendentes até o boss decidir; o banco nunca muda sozinho) ----
@router.get("/edicoes")
def edicoes(request: Request, ident: Identidade = SO_BOSS):
    """Edições feitas fora (Obsidian) esperando decisão do boss, com o texto novo."""
    con = _con(request)
    try:
        itens = [dict(r) for r in con.execute("select id, pessoa_id, arquivo, texto, criado_em from edicao_externa where estado='pendente' order by id")]
        return envelope(con, {"itens": itens}, agora=_agora(request))
    finally:
        con.close()


@router.post("/edicoes/{edicao_id}/decidir")
async def decidir_edicao(edicao_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Aprova (você aplicou o que mudou) ou rejeita (o arquivo volta ao exportado) uma edição externa."""
    corpo = _corpo(await _json(request))
    if corpo.get("estado") not in ("aprovada", "rejeitada"):
        raise erro(400, "requisicao_invalida", "estado deve ser aprovada ou rejeitada")
    con = _con(request)
    try:
        agora = _agora(request).astimezone(dt.timezone.utc).isoformat()
        n = con.execute("update edicao_externa set estado=?, decidida_em=? where id=? and estado='pendente'", (corpo["estado"], agora, edicao_id)).rowcount
        if not n:
            raise erro(404, "nao_encontrado", "edição não existe ou já foi decidida")
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')", (agora, ident.login, f"edição externa {edicao_id} {corpo['estado']}"))
        return envelope(con, {"id": edicao_id, "estado": corpo["estado"]}, agora=_agora(request))
    finally:
        con.close()
