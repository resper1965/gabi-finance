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
from gabi.escuta.classificar import recusa_sem_envio
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


def custo_padrao_usd() -> float:
    """Custo conservador de uma chamada que falhou depois do envio: OPENROUTER_CUSTO_PADRAO_USD (o mesmo do serviço de fontes), padrão 0,05."""
    try:
        v = float(os.environ.get("OPENROUTER_CUSTO_PADRAO_USD", CUSTO_RESERVA_USD))
    except ValueError:
        return CUSTO_RESERVA_USD
    return v if math.isfinite(v) and v > 0 else CUSTO_RESERVA_USD


PISO_RESERVA_USD = 0.001    # a reserva de falha nunca fica abaixo disto
FATOR_RESERVA = 5           # reserva = 5 x a mediana do custo real da própria tarefa
MIN_AMOSTRAS_RESERVA = 10   # com menos chamadas completadas que isto, vale o padrão conservador
JANELA_RESERVA = dt.timedelta(days=14)


def reserva_falha_usd(con, tarefa: str, agora: dt.datetime) -> float:
    """Custo a gravar quando uma chamada falha DEPOIS do envio. Seguir o custo real da tarefa (A6): a reserva fixa de US$ 0,05 contra
    chamadas de US$ 0,0001 fazia 20 timeouts por dia (US$ 1) estourarem o teto diário e bloquearem o modelo. Sem histórico suficiente, o padrão
    conservador (`custo_padrao_usd`) continua valendo, e ele também é o teto da reserva."""
    padrao = custo_padrao_usd()
    try:
        desde = (agora - JANELA_RESERVA).astimezone(BRT).isoformat()
        custos = sorted(r[0] for r in con.execute("select custo_usd from custo_modelo where tarefa=? and em>=?", (tarefa, desde)) if r[0] is not None)
    except sqlite3.Error:
        return padrao
    if len(custos) < MIN_AMOSTRAS_RESERVA:
        return padrao
    mediana = custos[len(custos) // 2]
    return min(padrao, max(PISO_RESERVA_USD, FATOR_RESERVA * mediana))


class ModeloComCusto:
    """Cada chamada COMPLETADA vira, NA HORA, uma linha em `custo_modelo` (tarefa `tarefa`, padrão 'escuta'; chamada que falhou depois do envio: tarefa
    '<tarefa>-falha' com custo conservador, `em` = instante da chamada em BRT), numa
    SEGUNDA conexão em autocommit (WAL + busy_timeout). O serviço de fontes já cobrou a chamada: se o insert falhar (lock), a
    classificação paga NÃO se perde; a linha fica pendente e é regravada na próxima chamada completada e em `fechar()`.
    Erro do cliente propaga (recusa antes do envio não grava)."""

    def __init__(self, cliente, banco: Path, relogio=None, tarefa: str = "escuta"):
        self._cliente, self._relogio, self._tarefa = cliente, relogio or (lambda: dt.datetime.now(dt.timezone.utc)), tarefa
        self._con = conectar(banco)
        self.pendentes: list[tuple[str, float]] = []

    def _gravar_pendentes(self) -> None:
        while self.pendentes:
            try:
                self._con.execute("insert into custo_modelo(em, custo_usd, tarefa) values (?,?,?)", self.pendentes[0])
            except sqlite3.Error:
                return
            self.pendentes.pop(0)

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        try:
            texto, custo = self._cliente.completar(prompt, forte=forte)
        except Exception as e:
            # I9: falha DEPOIS do envio pode ter sido faturada; sem esta linha o brain não enxerga o gasto e o teto não segura.
            # Recusa antes do envio (não configurado, teto, limite, prompt grande) não cobra nada.
            if recusa_sem_envio(e) is None:
                self.pendentes.append((self._relogio().astimezone(BRT).isoformat(), reserva_falha_usd(self._con, self._tarefa, self._relogio()), f"{self._tarefa}-falha"))
                self._gravar_pendentes()
            raise
        try:
            ok = isinstance(custo, (int, float)) and not isinstance(custo, bool) and math.isfinite(custo) and custo >= 0
        except TypeError:
            ok = False
        custo = float(custo) if ok else CUSTO_RESERVA_USD
        self.pendentes.append((self._relogio().astimezone(BRT).isoformat(), custo, self._tarefa))
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
