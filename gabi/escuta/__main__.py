"""Programa da escuta (timer de 5 min e gatilho por arquivo): ingere o spool do ouvinte, processa e imprime SÓ contagens.
O modelo e o Paperless chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); este processo não tem rede nem chave.
Todo parâmetro é DADO em `parametro` (JSON): escuta.modo, escuta.anexo_max_mb. Uso: python -m gabi.escuta"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.escuta.caixa import ingerir_spool
from gabi.escuta.destinos import DestinosReais
from gabi.escuta.processar import processar
from gabi.fontes.ponte import Ponte, PonteModelo

BRT = ZoneInfo("America/Sao_Paulo")
_AUTO = object()


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    if r is None:
        return padrao
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return padrao


def _modo(con) -> str:
    m = _parametro(con, "escuta.modo", "registro")
    return m if m in ("registro", "ativo") else "registro"


def _anexo_max_bytes(con) -> int:
    mb = _parametro(con, "escuta.anexo_max_mb", 25)
    if isinstance(mb, bool) or not isinstance(mb, (int, float)) or mb <= 0:
        mb = 25
    return int(mb * 1024 * 1024)


class ModeloComCusto:
    """Cada chamada COMPLETADA vira uma linha em `custo_modelo` (custo devolvido pelo cliente); erro propaga e não registra.
    As linhas são gravadas em `gravar()`, FORA da transação de cada mensagem: o rollback de uma mensagem não pode apagar gasto já feito."""

    def __init__(self, cliente, con, agora: dt.datetime):
        self._cliente, self._con, self._agora, self._pendentes = cliente, con, agora, []

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        texto, custo = self._cliente.completar(prompt, forte=forte)
        self._pendentes.append(float(custo))
        return texto, custo

    def gravar(self) -> None:
        em = self._agora.astimezone(BRT).isoformat()
        pendentes, self._pendentes = self._pendentes, []
        for custo in pendentes:
            self._con.execute("insert into custo_modelo(em, custo_usd, tarefa) values (?,?,'escuta')", (em, custo))


def cliente_da_ponte(socket_path: str | None):
    """Sem socket ou com o modelo não configurado na ponte: None (mensagens ficam `nova`; crise por palavra continua)."""
    if not socket_path:
        return None
    try:
        return PonteModelo(socket_path) if Ponte(socket_path, "openrouter").configurada() else None
    except Exception:  # noqa: BLE001 - ponte fora do ar nunca aborta a rodada
        return None


def main(banco: Path | None = None, *, cliente=_AUTO, paperless=None, agora: dt.datetime | None = None) -> int:
    spool = os.environ.get("GABI_ESCUTA_SPOOL")
    if not spool:
        print("ERRO: GABI_ESCUTA_SPOOL não configurado (pasta do spool do ouvinte)")
        return 2
    spool = Path(spool)
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    agora = agora or dt.datetime.now(dt.timezone.utc)
    sock = os.environ.get("GABI_FONTES_SOCKET")
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    if cliente is _AUTO:
        cliente = cliente_da_ponte(sock)
    if cliente is not None:
        cliente = ModeloComCusto(cliente, con, agora)
    if paperless is None and sock:
        paperless = Ponte(sock, "paperless")
    destinos = DestinosReais(paperless, spool=spool, anexo_max_bytes=_anexo_max_bytes(con))
    agora_s = agora.astimezone(dt.timezone.utc).isoformat()
    novas = ingerir_spool(con, spool, agora_s)
    try:
        r = processar(con, destinos, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), agora_s, modo=_modo(con), spool=spool)
    finally:
        if isinstance(cliente, ModeloComCusto):
            cliente.gravar()
    print(f"escuta: ingeridas={novas} " + " ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
