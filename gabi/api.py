"""API do gabi.brain (Fase 0): identidade, saúde, segurança e revogação. Toda chamada /api/* é registrada (R4)."""
import datetime as dt
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from gabi.db import conectar, migrar
from gabi.identidade import Identidade, exigir, normalizar_login

AQUI = Path(__file__).resolve().parent
MIGRACOES = AQUI.parent / "migrations"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _con(request: Request):
    return conectar(Path(request.app.state.banco))


def _gravar_chamada(banco: Path, login: str | None, metodo: str, caminho: str, status: int) -> None:
    con = conectar(banco)
    try:
        con.execute("insert into chamada(quando, login, metodo, caminho, status) values (?,?,?,?,?)",
                    (_agora(), normalizar_login(login)[:200] if login and login.strip() else None,
                     metodo, caminho, status))
    finally:
        con.close()


def _recusa(status: int, erro: str, mensagem: str) -> JSONResponse:
    return JSONResponse({"erro": erro, "mensagem": mensagem}, status_code=status)


def _guarda_csrf(request: Request) -> JSONResponse | None:
    """A identidade vem da rede, então POST de outro site (CSRF) precisa ser barrado: só JSON, só same-origin."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    com_corpo = request.headers.get("content-length", "0") not in ("0", "") or "transfer-encoding" in request.headers
    if com_corpo and not request.headers.get("content-type", "").lower().startswith("application/json"):
        return _recusa(415, "tipo_invalido", "Envie o corpo como application/json.")
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return _recusa(403, "nao_permitido", "Requisição de outro site recusada.")
    origem = request.headers.get("origin")
    if origem and urlsplit(origem).netloc != request.headers.get("host", ""):
        return _recusa(403, "nao_permitido", "Requisição de outra origem recusada.")
    return None


def criar_app(banco: Path, permite_tcp_local: bool = False, relogio=None) -> FastAPI:
    """permite_tcp_local=False é o padrão de produção: só o socket Unix do serviço é origem confiável."""
    app = FastAPI(title="gabi.brain", docs_url=None, redoc_url=None)
    app.state.banco = Path(banco)
    app.state.permite_tcp_local = permite_tcp_local
    app.state.relogio = relogio or (lambda: dt.datetime.now(ZoneInfo("America/Sao_Paulo")))  # injetável nos testes

    @app.exception_handler(HTTPException)
    async def erro_http(_request: Request, exc: HTTPException):
        corpo = exc.detail if isinstance(exc.detail, dict) else {"erro": "erro", "mensagem": str(exc.detail)}
        return JSONResponse(corpo, status_code=exc.status_code)

    @app.middleware("http")
    async def registrar_chamada(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        status = 500
        try:
            resposta = _guarda_csrf(request) or await call_next(request)
            status = resposta.status_code
            return resposta
        finally:  # R4: registra também o 500; falha no log nunca troca a resposta
            try:
                _gravar_chamada(app.state.banco, request.headers.get("Tailscale-User-Login"),
                                request.method, request.url.path, status)
            except Exception:
                logging.getLogger("gabi.api").exception("falha ao registrar chamada")

    @app.get("/api/eu")
    def eu(i: Identidade = Depends(exigir("terceiros"))):
        return {"login": i.login, "pessoa_id": i.pessoa_id, "nivel": i.nivel}

    @app.get("/api/saude")
    def saude(request: Request, _: Identidade = Depends(exigir("boss"))):
        con = _con(request)
        try:
            tabelas = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table' and name not like '%\\_fts%' escape '\\' "
                "and name not like 'sqlite_%' order by name")]
            ultima = con.execute("select id, fonte, inicio, fim, status, lidos, novos, alterados "
                                 "from rodada order by id desc limit 1").fetchone()
            return {
                "db": "ok" if con.execute("pragma quick_check").fetchone()[0] == "ok" else "corrompido",
                "schema": con.execute("select count(*) from schema_versao").fetchone()[0],
                "ultima_rodada": dict(ultima) if ultima else None,
                "tabelas": {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tabelas},
            }
        finally:
            con.close()

    @app.get("/api/seguranca")
    def seguranca(request: Request, _: Identidade = Depends(exigir("boss"))):
        con = _con(request)
        try:
            desde = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            backup = con.execute("select fonte, inicio, fim, status from rodada "
                                 "where fonte='backup' and status='ok' order by id desc limit 1").fetchone()
            return {
                "acessos": [dict(r) for r in con.execute(
                    "select login, pessoa_id, nivel from acesso order by login")],
                "tokens_ativos": con.execute(
                    "select count(*) from token_agente where revogado_em is null").fetchone()[0],
                "chamadas_24h": con.execute("select count(*) from chamada where quando >= ?", (desde,)).fetchone()[0],
                "ultimo_backup": dict(backup) if backup else None,
            }
        finally:
            con.close()

    @app.post("/api/revogar-tudo")
    async def revogar_tudo(request: Request, i: Identidade = Depends(exigir("boss"))):
        try:
            corpo = await request.json()
        except Exception:
            corpo = None
        if not isinstance(corpo, dict) or corpo.get("confirmo") is not True:
            raise HTTPException(400, detail={"erro": "confirmacao_ausente",
                                             "mensagem": 'Envie {"confirmo": true} para revogar tudo.'})
        con = _con(request)
        try:
            n = con.execute("update token_agente set revogado_em=? where revogado_em is null", (_agora(),)).rowcount
            con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?,?)",
                        (_agora(), i.login, f"revogar tudo: {n} token(s) de agente", "api"))
        finally:
            con.close()
        return {"revogados": n}

    @app.get("/")
    def raiz(_: Identidade = Depends(exigir("terceiros"))):
        return FileResponse(AQUI / "static" / "index.html")

    from gabi.rotas.dinheiro import router as rotas_dinheiro
    app.include_router(rotas_dinheiro)
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    return app


def fabrica() -> FastAPI:
    """uvicorn --factory gabi.api:fabrica --uds ... ; banco em GABI_BANCO. TCP local só com GABI_PERMITE_TCP_LOCAL=1 (dev)."""
    banco = Path(os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    con = conectar(banco)
    try:
        migrar(con, MIGRACOES)
    finally:
        con.close()
    return criar_app(banco, permite_tcp_local=os.environ.get("GABI_PERMITE_TCP_LOCAL") == "1")
