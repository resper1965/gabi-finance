"""Programa da escuta (timer de 5 min e gatilho por arquivo): ingere o spool do ouvinte, processa e imprime SÓ contagens.
O modelo e o Paperless chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); este processo não tem rede nem chave.
Todo parâmetro é DADO em `parametro` (JSON): escuta.modo, escuta.anexo_max_mb. Uso: python -m gabi.escuta"""
import datetime as dt
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.escuta.caixa import ingerir_spool, limpar_orfaos
from gabi.escuta.crise import escrever_palavras_risco
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


CUSTO_RESERVA_USD = 0.05  # custo inválido (NaN, infinito, negativo) nunca subnotifica o gasto: grava este valor fixo


class ModeloComCusto:
    """Cada chamada COMPLETADA vira, NA HORA, uma linha em `custo_modelo` (tarefa 'escuta', `em` = instante da chamada em BRT), numa
    SEGUNDA conexão em autocommit (WAL + busy_timeout). O serviço de fontes já cobrou a chamada: se o insert falhar (lock), a
    classificação paga NÃO se perde; a linha fica pendente e é regravada na próxima chamada completada e em `fechar()`.
    Erro do cliente propaga e não grava."""

    def __init__(self, cliente, banco: Path, relogio=None):
        self._cliente, self._relogio = cliente, relogio or (lambda: dt.datetime.now(dt.timezone.utc))
        self._con = conectar(banco)
        self.pendentes: list[tuple[str, float]] = []

    def _gravar_pendentes(self) -> None:
        while self.pendentes:
            try:
                self._con.execute("insert into custo_modelo(em, custo_usd, tarefa) values (?,?,'escuta')", self.pendentes[0])
            except sqlite3.Error:
                return
            self.pendentes.pop(0)

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        texto, custo = self._cliente.completar(prompt, forte=forte)
        try:
            ok = isinstance(custo, (int, float)) and not isinstance(custo, bool) and math.isfinite(custo) and custo >= 0
        except TypeError:
            ok = False
        custo = float(custo) if ok else CUSTO_RESERVA_USD
        self.pendentes.append((self._relogio().astimezone(BRT).isoformat(), custo))
        self._gravar_pendentes()
        return texto, custo

    def fechar(self) -> None:
        self._gravar_pendentes()
        if self.pendentes:  # só a contagem, nunca valores
            print(f"AVISO: {len(self.pendentes)} linha(s) de custo_modelo não gravada(s)", file=sys.stderr)
        self._con.close()


def cliente_da_ponte(socket_path: str | None):
    """Sem socket ou com o modelo não configurado na ponte: None (mensagens ficam `nova`; crise por palavra continua)."""
    if not socket_path:
        return None
    try:
        return PonteModelo(socket_path) if Ponte(socket_path, "openrouter").configurada() else None
    except Exception:  # noqa: BLE001 - ponte fora do ar nunca aborta a rodada
        return None


def main(banco: Path | None = None, *, cliente=_AUTO, paperless=None, agora: dt.datetime | None = None, relogio=None) -> int:
    spool = os.environ.get("GABI_ESCUTA_SPOOL")
    if not spool:
        print("ERRO: GABI_ESCUTA_SPOOL não configurado (pasta do spool do ouvinte)", file=sys.stderr)
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
        cliente = ModeloComCusto(cliente, banco, relogio)
    if paperless is None and sock:
        paperless = Ponte(sock, "paperless")
    destinos = DestinosReais(paperless, spool=spool, anexo_max_bytes=_anexo_max_bytes(con))
    agora_s = agora.astimezone(dt.timezone.utc).isoformat()
    try:  # o ouvinte lê a lista de risco deste arquivo; spool sem escrita nunca aborta a rodada
        palavras_erro = 0
        escrever_palavras_risco(con, spool)
    except Exception:  # noqa: BLE001
        palavras_erro = 1
    novas = ingerir_spool(con, spool, agora_s)
    try:
        r = processar(con, destinos, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), agora_s, modo=_modo(con), spool=spool)
    finally:
        if isinstance(cliente, ModeloComCusto):
            cliente.fechar()
    orfaos = limpar_orfaos(con, spool)  # último passo: anexo que nenhuma mensagem aponta mais (a API só anula o ponteiro)
    print(f"escuta: ingeridas={novas} " + " ".join(f"{k}={v}" for k, v in r.items()) + f" orfaos={orfaos} palavras_erro={palavras_erro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
