"""Identidade pelo cabeçalho do `tailscale serve` (Tailscale-User-Login). R3: só vale vindo do socket Unix do serviço."""
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


def origem_confiavel(request: Request) -> bool:
    """Produção: só conexão por socket Unix (pasta 0700; quem chega ali é o tailscaled). TCP local só em dev/teste."""
    client, server = request.scope.get("client"), request.scope.get("server")
    if client is None and server is not None and server[1] is None:
        return True  # socket Unix: o ASGI não informa porta
    permite_tcp = getattr(request.app.state, "permite_tcp_local", False)
    return bool(permite_tcp and client is not None and client[0] in HOSTS_LOCAIS)


def exigir(nivel_minimo: str = "terceiros"):
    """Dependência FastAPI: 403 se a origem não é confiável, 401 sem cabeçalho, 403 login desconhecido ou nível baixo."""
    def dependencia(request: Request) -> Identidade:
        if not origem_confiavel(request):
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


GRAUS = ("nenhum", "parcial", "total")


def grau(con: sqlite3.Connection, informacao: str, nivel: str) -> str:
    """Quanto o nível enxerga da informação, pela `matriz_acesso` ('nenhum' | 'parcial' | 'total'). Sem linha na matriz: só o boss vê (nega por padrão)."""
    r = con.execute("select boss, familia_vip, terceiros from matriz_acesso where informacao=?", (informacao,)).fetchone()
    valor = r[nivel] if r is not None else ("total" if nivel == "boss" else "nenhum")
    return valor if valor in GRAUS else "nenhum"


def exigir_informacao(informacao: str, grau_minimo: str = "parcial"):
    """Dependência FastAPI para dado que a matriz libera por nível (ex.: saúde): 403 se o grau do nível for menor que o pedido.
    O handler que devolve dado `parcial` decide o recorte (só a própria pessoa, sem campos sensíveis)."""
    base = exigir("terceiros")

    def dependencia(request: Request) -> Identidade:
        ident = base(request)
        con = conectar(Path(request.app.state.banco))
        try:
            g = grau(con, informacao, ident.nivel)
        finally:
            con.close()
        if GRAUS.index(g) < GRAUS.index(grau_minimo) or g == "nenhum":
            raise HTTPException(403, detail={"erro": "sem_escopo", "mensagem": "Você não tem acesso a isto."})
        return ident
    return dependencia
