"""Rotas /api/v1/familia: exames (T4.2). A saúde vive em arquivo próprio e criptografado (ADR-014), nunca no banco principal.
Quem vê o quê vem da matriz_acesso ('saúde'): total = todos; parcial = só a própria pessoa; nenhum = 403. Todo acesso entra no log do cofre.
Enviar/confirmar/rejeitar laudo: só boss com grau total. Consome: familia.{saude,exames}, identidade, fontes (Paperless, pela ponte)."""
import datetime as dt
import threading

from fastapi import APIRouter, Depends, Request

from gabi.envelope import envelope
from gabi.familia import exames
from gabi.familia.saude import abrir_saude, marcadores, pode_ver, resumo_para_consulta, serie
from gabi.identidade import Identidade, exigir_informacao, grau
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

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
    return _resp(request, {"pessoa_id": pessoa_id, "marcadores": itens})


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


@router.get("/laudos")
def laudos(request: Request, ident: Identidade = SO_BOSS):
    """Laudos lidos do Paperless esperando a confirmação de quem é o laudo (só boss)."""
    with _TRAVA, _cofre(request) as s:
        itens = exames.laudos_pendentes(s)
    return _resp(request, {"itens": itens})


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
        n = exames.propor_exames(s, pid, docs[0].get("content") or "", corpo.get("pessoa_sugerida"))
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
    return _resp(request, {"paperless_id": paperless_id, "exames": n})


@router.post("/laudos/{paperless_id}/rejeitar")
async def rejeitar(paperless_id: int, request: Request, ident: Identidade = SO_BOSS):
    """Descarta as propostas de um laudo sem registrar nenhum exame."""
    with _TRAVA, _cofre(request) as s:
        n = exames.rejeitar_laudo(s, paperless_id)
    return _resp(request, {"paperless_id": paperless_id, "rejeitadas": n})
