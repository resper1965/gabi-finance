"""Identidade pelo cabeçalho do `tailscale serve` (Tailscale-User-Login). R3: só vale vindo de localhost."""
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from gabi.db import conectar

NIVEIS = ("terceiros", "familia_vip", "boss")  # do menor para o maior
HOSTS_LOCAIS = {"127.0.0.1", "::1"}


@dataclass(frozen=True)
class Identidade:
    login: str
    pessoa_id: str | None
    nivel: str


def normalizar_login(login: str) -> str:
    return login.strip().lower()


def nivel_suficiente(atual: str, minimo: str) -> bool:
    return NIVEIS.index(atual) >= NIVEIS.index(minimo)


def resolver(con: sqlite3.Connection, login: str | None) -> Identidade | None:
    if not login or not login.strip():
        return None
    login = normalizar_login(login)
    r = con.execute("select login, pessoa_id, nivel from acesso where login=?", (login,)).fetchone()
    return Identidade(r["login"], r["pessoa_id"], r["nivel"]) if r else None


def exigir(nivel_minimo: str = "terceiros"):
    """Dependência FastAPI: 403 fora de localhost, 401 sem cabeçalho, 403 login desconhecido ou nível baixo."""
    def dependencia(request: Request) -> Identidade:
        host = request.client.host if request.client else None
        if host not in HOSTS_LOCAIS:
            raise HTTPException(403, detail={"erro": "nao_permitido", "mensagem": "Acesso só pelo Tailscale."})
        login = request.headers.get("Tailscale-User-Login")
        if not login or not login.strip():
            raise HTTPException(401, detail={"erro": "nao_autenticado", "mensagem": "Identidade ausente."})
        con = conectar(Path(request.app.state.banco))
        try:
            ident = resolver(con, login)
        finally:
            con.close()
        if ident is None or not nivel_suficiente(ident.nivel, nivel_minimo):
            raise HTTPException(403, detail={"erro": "sem_escopo", "mensagem": "Você não tem acesso a isto."})
        request.state.identidade = ident
        return ident
    return dependencia
