"""Cliente de modelo do correio: chamada com teto (`_chamar`), recusas sem envio, custo gravado por chamada (`ModeloComCusto`) e o
cliente pela ponte do serviço de fontes. Veio de gabi/escuta (ADR-023): o correio é o único usuário. Consome: fontes.ponte, dinheiro.modelo."""
import datetime as dt
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import conectar
from gabi.dinheiro.modelo import Orcamento
from gabi.fontes.ponte import Ponte, PonteModelo

BRT = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class Falha:
    """Não classificou. `temporaria`: vale tentar de novo com espera (exceção/timeout/resposta vazia, possivelmente cobrada).
    Não temporária: sem modelo, teto ou limite (o aviso `escuta_sem_modelo` cobre; não conta tentativa). `motivo` é curto e fixo,
    nunca texto de mensagem nem do erro."""
    motivo: str
    temporaria: bool


# Recusas que acontecem ANTES do envio ao modelo (nada foi cobrado; não são falha temporária). Trecho da mensagem -> motivo curto.
RECUSAS_SEM_ENVIO = {"não está configurado": "modelo não configurado", "chave ausente": "modelo não configurado",
                     "teto diário": "teto diário do serviço de modelo", "muitas chamadas": "limite de chamadas por minuto",
                     "prompt grande demais": "mensagem grande demais para o modelo",
                     "pdf inválido": "PDF inválido", "pdf grande demais": "PDF grande demais", "pdf com páginas demais": "PDF com páginas demais"}


def recusa_sem_envio(e: BaseException) -> str | None:
    from gabi.fontes.openrouter import ErroOpenRouter
    if not isinstance(e, ErroOpenRouter):
        return None
    msg = str(e)
    return next((motivo for trecho, motivo in RECUSAS_SEM_ENVIO.items() if trecho in msg), None)


def _chamar(cliente, prompt: str, forte: bool, orcamento: Orcamento) -> "str | Falha":
    if not orcamento.permite():
        return Falha("teto de custo do modelo", False)
    try:
        texto, custo = cliente.completar(prompt, forte=forte)
    except Exception as e:  # noqa: BLE001 - nunca derruba a rodada; a mensagem do erro não sai daqui
        motivo = recusa_sem_envio(e)
        return Falha(motivo, False) if motivo else Falha("falha temporária do modelo", True)
    orcamento.registrar(custo)
    if not isinstance(texto, str) or not texto.strip():
        return Falha("resposta vazia do modelo", True)  # cobrada e sem conteúdo: tenta de novo, nunca 'nada'
    return texto


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

    def __init__(self, cliente, banco: Path, relogio=None, tarefa: str = "escuta", tarefa_visao: str | None = None):
        self._cliente, self._relogio, self._tarefa = cliente, relogio or (lambda: dt.datetime.now(dt.timezone.utc)), tarefa
        self._tarefa_visao = tarefa_visao or f"{tarefa}-visao"  # leitura de PDF por imagem tem custo próprio (exames-visao, reembolso-visao)
        self._con = conectar(banco)
        self.pendentes: list[tuple[str, float]] = []

    def _gravar_pendentes(self) -> None:
        while self.pendentes:
            try:
                self._con.execute("insert into custo_modelo(em, custo_usd, tarefa) values (?,?,?)", self.pendentes[0])
            except sqlite3.Error:
                return
            self.pendentes.pop(0)

    def _registrar(self, tarefa: str, chamada) -> tuple[str, float]:
        try:
            texto, custo = chamada()
        except Exception as e:
            # I9: falha DEPOIS do envio pode ter sido faturada; sem esta linha o brain não enxerga o gasto e o teto não segura.
            # Recusa antes do envio (não configurado, teto, limite, prompt grande, PDF inválido ou grande) não cobra nada.
            if recusa_sem_envio(e) is None:
                self.pendentes.append((self._relogio().astimezone(BRT).isoformat(), reserva_falha_usd(self._con, tarefa, self._relogio()), f"{tarefa}-falha"))
                self._gravar_pendentes()
            raise
        try:
            ok = isinstance(custo, (int, float)) and not isinstance(custo, bool) and math.isfinite(custo) and custo >= 0
        except TypeError:
            ok = False
        custo = float(custo) if ok else CUSTO_RESERVA_USD
        self.pendentes.append((self._relogio().astimezone(BRT).isoformat(), custo, tarefa))
        self._gravar_pendentes()
        return texto, custo

    def completar(self, prompt: str, *, forte: bool) -> tuple[str, float]:
        return self._registrar(self._tarefa, lambda: self._cliente.completar(prompt, forte=forte))

    @property
    def completar_pdf(self):
        """Só existe se o cliente de baixo sabe ler PDF (quem chama testa com getattr: sem o método, o PDF sem texto continua `falhou`)."""
        interno = getattr(self._cliente, "completar_pdf", None)
        if not callable(interno):
            raise AttributeError("completar_pdf")

        def completar_pdf(pdf: bytes, prompt: str, *, forte: bool = False, **tetos) -> tuple[str, float]:
            return self._registrar(self._tarefa_visao, lambda: interno(pdf, prompt, forte=forte, **tetos))
        return completar_pdf

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
