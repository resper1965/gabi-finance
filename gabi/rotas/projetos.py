"""Projetos (/api/v1/projetos e /api/v1/anexos): gestão de projetos do Ricardo (ADR-034): criar, ver, atualizar, pessoas, gastos, fatos e anexos.

Só chama `gabi.projetos` (as regras moram lá); `quem` = login, `origem` = 'painel'. `LookupError` → 404 `nao_encontrado`; `ValueError` → 400 `requisicao_invalida`.
Dinheiro entra como o Ricardo dita ("1.500,00", string) e sai em string decimal de reais; datas em Brasília (`AAAA-MM-DD`). O original do anexo sai de `ANEXOS_DIR` (só o boss).
Consome: projetos, envelope, identidade."""
import mimetypes
import os
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from gabi import projetos
from gabi.anexos import DESTINO_PADRAO
from gabi.cobrar.receber_manual import ErroReceber, valor_ditado
from gabi.envelope import envelope
from gabi.identidade import Identidade, exigir
from gabi.rotas.dinheiro import _agora, _con, _corpo, _json, erro

router = APIRouter(prefix="/api/v1/projetos", dependencies=[Depends(exigir("boss"))])
router_anexos = APIRouter(prefix="/api/v1/anexos", dependencies=[Depends(exigir("boss"))])
TIPOS = {".heic": "image/heic", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".aac": "audio/aac"}


def _so(corpo: dict, permitidos: set) -> None:
    extra = set(corpo) - permitidos
    if extra:
        raise erro(400, "requisicao_invalida", f"campos desconhecidos: {sorted(extra)}")


def _texto(corpo: dict, campo: str, obrigatorio: bool = False, padrao=None):
    v = corpo.get(campo)
    if v is None:
        if obrigatorio:
            raise erro(400, "requisicao_invalida", f"{campo} é obrigatório")
        return padrao
    if not isinstance(v, str):
        raise erro(400, "requisicao_invalida", f"{campo} deve ser texto")
    return v


def _inteiro(corpo: dict, campo: str):
    v = corpo.get(campo)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise erro(400, "requisicao_invalida", f"{campo} deve ser um número inteiro")
    return v


def _valor(corpo: dict, campo: str):
    v = _texto(corpo, campo)
    if v is None:
        return None
    try:
        return valor_ditado(v)
    except ErroReceber as e:
        raise erro(400, "requisicao_invalida", e.mensagem)


def _rodar(request: Request, faz: Callable) -> dict:
    """Roda a regra com a conexão e devolve o envelope; traduz os erros das regras para HTTP."""
    con = _con(request)
    try:
        try:
            dados = faz(con, _agora(request))
        except LookupError as e:
            raise erro(404, "nao_encontrado", str(e).strip("'\""))
        except ValueError as e:
            raise erro(400, "requisicao_invalida", str(e))
        return envelope(con, dados, agora=_agora(request))
    finally:
        con.close()


@router.get("")
def listar(request: Request, status: str = "ativo"):
    """Projetos por status (ativo, pausado, concluido ou cancelado), com o progresso (`feitas` de `total` atividades)."""
    return _rodar(request, lambda con, agora: {"itens": projetos.listar(con, agora, status)})


@router.post("", status_code=201)
async def criar(request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Cria o projeto: `nome` e, opcional, `objetivo`, `prazo` (AAAA-MM-DD), `orcamento` (reais, string) e `atividades` (até 30: `texto`, `vence`, `depois_de` índice anterior, `marco`). Tudo ou nada."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"nome", "objetivo", "prazo", "orcamento", "atividades"})
    nome, objetivo, prazo = _texto(corpo, "nome", True), _texto(corpo, "objetivo", padrao=""), _texto(corpo, "prazo")
    orcamento, lista = _valor(corpo, "orcamento"), corpo.get("atividades")
    if lista is not None and not isinstance(lista, list):
        raise erro(400, "requisicao_invalida", "atividades deve ser uma lista")

    def faz(con, agora):
        novo = projetos.criar(con, agora, ident.login, "painel", nome, objetivo, prazo, orcamento, lista)
        return projetos.ver(con, agora, novo["id"])
    return _rodar(request, faz)


@router.get("/{id_}")
def ver(id_: int, request: Request):
    """O resumo do projeto: progresso, próximas, bloqueadas, atrasadas, pessoas, orçamento/gasto/saldo, últimos fatos e a contagem de anexos."""
    return _rodar(request, lambda con, agora: projetos.ver(con, agora, id_))


@router.patch("/{id_}")
async def atualizar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Atualiza `status`, `prazo`, `objetivo`, `orcamento` ou `nome`. Concluído e cancelado não reabrem; cancelar cancela as atividades abertas."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"status", "prazo", "objetivo", "orcamento", "nome"})
    campos = {c: _texto(corpo, c) for c in ("status", "prazo", "objetivo", "nome")}
    orcamento = _valor(corpo, "orcamento")

    def faz(con, agora):
        projetos.atualizar(con, agora, ident.login, "painel", id_, orcamento_centavos=orcamento, **campos)
        return projetos.ver(con, agora, id_)
    return _rodar(request, faz)


@router.post("/{id_}/pessoas", status_code=201)
async def pessoa(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Adiciona uma pessoa ao projeto: `nome`, `papel`, `contato` e, opcional, `pessoa_id` do cadastro da família."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"nome", "papel", "contato", "pessoa_id"})
    nome, papel, contato, pid = _texto(corpo, "nome", True), _texto(corpo, "papel", padrao=""), _texto(corpo, "contato", padrao=""), _texto(corpo, "pessoa_id")
    return _rodar(request, lambda con, agora: projetos.adicionar_pessoa(con, agora, ident.login, "painel", id_, nome, papel, contato, pid))


@router.post("/{id_}/gastos", status_code=201)
async def gasto(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Registra um gasto: `valor` (reais, string) manual ou `lancamento_id` do banco (o valor vem dele); nunca os dois."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"valor", "descricao", "data", "lancamento_id"})
    valor, desc, data, lanc = _valor(corpo, "valor"), _texto(corpo, "descricao", padrao=""), _texto(corpo, "data"), _inteiro(corpo, "lancamento_id")
    return _rodar(request, lambda con, agora: projetos.adicionar_gasto(con, agora, ident.login, "painel", id_, valor_centavos=valor, descricao=desc, data=data, lancamento_id=lanc))


@router.post("/{id_}/fatos", status_code=201)
async def fato(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Anota um fato (até 1.000 caracteres) com `data` (padrão hoje), `pessoa_nome`, `anexo_id` e `atividade_id` opcionais."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"texto", "data", "pessoa_nome", "anexo_id", "atividade_id"})
    texto, data, pessoa_nome = _texto(corpo, "texto", True), _texto(corpo, "data"), _texto(corpo, "pessoa_nome", padrao="")
    anexo, ativ = _inteiro(corpo, "anexo_id"), _inteiro(corpo, "atividade_id")
    return _rodar(request, lambda con, agora: projetos.registrar_fato(con, agora, ident.login, "painel", id_, texto, data, pessoa_nome, anexo, ativ))


@router.post("/{id_}/anexos", status_code=201)
async def anexar(id_: int, request: Request, ident: Identidade = Depends(exigir("boss"))):
    """Liga ao projeto um anexo da caixa de entrada (`anexo_id`) ou um documento do Paperless (`paperless_id`); um dos dois."""
    corpo = _corpo(await _json(request))
    _so(corpo, {"anexo_id", "paperless_id"})
    anexo, paperless = _inteiro(corpo, "anexo_id"), _inteiro(corpo, "paperless_id")
    return _rodar(request, lambda con, agora: projetos.anexar(con, agora, ident.login, "painel", id_, anexo, paperless))


@router_anexos.get("/recentes")
def recentes(request: Request):
    """A caixa de entrada: anexos dos últimos 14 dias ainda sem projeto (com a transcrição do áudio, quando houver)."""
    return _rodar(request, lambda con, agora: {"itens": projetos.anexos_recentes(con, agora)})


@router_anexos.get("/{id_}/arquivo")
def arquivo(id_: int, request: Request):
    """O original do anexo (imagem ou áudio), sem mascarar; 404 se o anexo não existe, é documento do Paperless ou o arquivo sumiu."""
    con = _con(request)
    try:
        r = con.execute("select arquivo from anexo where id=?", (id_,)).fetchone()
    finally:
        con.close()
    if r is None:
        raise erro(404, "nao_encontrado", f"anexo {id_} não existe")
    base = Path(os.environ.get("ANEXOS_DIR") or DESTINO_PADRAO).resolve()
    caminho = (base / r["arquivo"]).resolve() if r["arquivo"] else None
    if caminho is None or base not in caminho.parents or not caminho.is_file():
        raise erro(404, "nao_encontrado", "o arquivo desse anexo não está no disco")
    tipo = TIPOS.get(caminho.suffix.lower()) or mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    return FileResponse(caminho, media_type=tipo)
