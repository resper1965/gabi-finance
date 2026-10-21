"""Programa da escuta (timer de 5 min e gatilho por arquivo): ingere o spool do ouvinte, processa e imprime SÓ contagens.
O modelo e o Paperless chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); este processo não tem rede nem chave.
Todo parâmetro é DADO em `parametro` (JSON): escuta.modo, escuta.anexo_max_mb, escuta.tempo_max_s, escuta.retida_dias, escuta.retencao_dias.
Uso: python -m gabi.escuta  |  python -m gabi.escuta --teste-crise (grava um aviso de crise de teste, nome TESTE)"""
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
from gabi.escuta.caixa import ingerir_spool, limpar_orfaos, purgar_antigas
from gabi.correio.modelo import ModeloComCusto, cliente_da_ponte  # noqa: F401
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


def _tempo_max_s(con) -> float:
    v = _parametro(con, "escuta.tempo_max_s", TEMPO_MAX_S)
    return v if not isinstance(v, bool) and isinstance(v, (int, float)) and v > 0 else TEMPO_MAX_S


def _dias(con, chave: str, padrao: int) -> int:
    v = _parametro(con, chave, padrao)
    return int(v) if not isinstance(v, bool) and isinstance(v, (int, float)) and v >= 1 else padrao


TEMPO_MAX_S = 420  # abaixo do TimeoutStartSec=600 da unit: a rodada para limpa antes de ser morta


def teste_crise(banco: Path, agora: dt.datetime) -> None:
    """Grava UM aviso `escuta_atencao` de teste (número e nome "TESTE", sem texto) para conferir que a crise chega ao Telegram/Hermes."""
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    con.execute("insert into aviso(tipo, payload, criado_em) values ('escuta_atencao', ?, ?)",
                (json.dumps({"numero": "TESTE", "nome": "TESTE"}), agora.astimezone(dt.timezone.utc).isoformat()))
    con.close()


def main(banco: Path | None = None, *, cliente=_AUTO, paperless=None, agora: dt.datetime | None = None, relogio=None,
         argv: list[str] | None = None) -> int:
    if argv and argv[0] == "--teste-crise":
        teste_crise(Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db")), agora or dt.datetime.now(dt.timezone.utc))
        print("escuta: aviso de crise de teste gravado (nome TESTE)")
        return 0
    if argv:
        print("uso: python -m gabi.escuta [--teste-crise]", file=sys.stderr)
        return 2
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
        r = processar(con, destinos, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), agora_s, modo=_modo(con), spool=spool,
                      tempo_max_s=_tempo_max_s(con), retida_dias=_dias(con, "escuta.retida_dias", 14))
    finally:
        if isinstance(cliente, ModeloComCusto):
            cliente.fechar()
    purgadas = purgar_antigas(con, agora_s, dias=_dias(con, "escuta.retencao_dias", 30))  # M6: grupo/nada processadas antigas
    orfaos = limpar_orfaos(con, spool)  # último passo: anexo que nenhuma mensagem aponta mais (a API só anula o ponteiro)
    print(f"escuta: ingeridas={novas} " + " ".join(f"{k}={v}" for k, v in r.items())
          + f" purgadas={purgadas} orfaos={orfaos} palavras_erro={palavras_erro}")
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
