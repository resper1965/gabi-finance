"""Rodadas do dinheiro: extratos (captura -> conferência -> classificação -> compromissos) e saldos (de hora em hora).

Uma rodada por fonte por vez (flock). O dados_ate só avança se a rodada de extratos for CONFERIDA.
Uso: python -m gabi.dinheiro.rodar extratos [--sincronizar] | saldos     (timers systemd; a chave vem de MCPAI_KEY)
Consome: dinheiro.{captura,conferencia,classificar,contas_pagar,repositorio}, fontes.mcpai.
"""
import datetime as dt
import fcntl
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.cobrar.recebimentos import propor_recebimentos
from gabi.db import conectar, migrar
from gabi.dinheiro import repositorio
from gabi.dinheiro.captura import ResumoCaptura, capturar, capturar_saldos
from gabi.dinheiro.classificar import ResumoClassificacao, classificar_pendentes
from gabi.dinheiro.conferencia import conferir, marcar_conferida
from gabi.dinheiro.contas_pagar import ResumoCompromissos, atualizar_compromissos


class RodadaEmAndamento(RuntimeError):
    """Já existe uma rodada desta fonte rodando."""


@contextmanager
def _lock(pasta: Path, nome: str):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    f = open(pasta / f"{nome}.lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RodadaEmAndamento(f"já há uma rodada de {nome} em andamento")
        yield
    finally:
        f.close()  # fechar libera o lock, mesmo em erro


@dataclass
class ResultadoExtratos:
    captura: ResumoCaptura
    conferida: bool
    classificacao: ResumoClassificacao
    compromissos: ResumoCompromissos


def rodar_extratos(con, cliente, hoje: dt.date, agora: dt.datetime, bruto_base: Path, pasta_locks: Path, *, sincronizar_antes: bool = False,
                   bancos_pj=None, dorme=time.sleep) -> ResultadoExtratos:
    with _lock(pasta_locks, "extratos"):
        if bancos_pj is None:
            bancos_pj = repositorio.ler_leitura(con)["params"]["bancos_pj"]
        captura = capturar(con, cliente, hoje, agora, bruto_base, bancos_pj=bancos_pj, sincronizar_antes=sincronizar_antes, dorme=dorme)
        for (cid,) in con.execute("select id from conta where excluido_em is null order by id").fetchall():
            conferir(con, captura.rodada_id, cid, hoje)
        conferida = marcar_conferida(con, captura.rodada_id)
        resultado = ResultadoExtratos(captura, conferida, classificar_pendentes(con), atualizar_compromissos(con, hoje, agora))
        propor_recebimentos(con)  # crédito em conta PJ x NFS-e autorizada: só PROPÕE (R1)
        return resultado


def rodar_saldos(con, cliente, agora: dt.datetime, pasta_locks: Path, bancos_pj=None) -> int:
    with _lock(pasta_locks, "saldos"):
        if bancos_pj is None:
            bancos_pj = repositorio.ler_leitura(con)["params"]["bancos_pj"]
        return capturar_saldos(con, cliente, agora, bancos_pj)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("extratos", "saldos"):
        print("uso: python -m gabi.dinheiro.rodar extratos [--sincronizar] | saldos")
        return 2
    from gabi.fontes.mcpai import Cliente, ErroMcpAi
    raiz = Path(os.environ.get("GABI_DADOS", "/var/lib/gabi-brain"))
    con = conectar(Path(os.environ.get("GABI_BANCO", raiz / "gabi.db")))
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    agora = dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    try:
        if argv[0] == "saldos":
            print(f"saldos: {rodar_saldos(con, Cliente(), agora, raiz / 'locks')} conta(s)")
            return 0
        r = rodar_extratos(con, Cliente(), agora.date(), agora, raiz / "bruto", raiz / "locks", sincronizar_antes="--sincronizar" in argv)
        c = r.captura
        print(f"extratos: contas={c.contas} lidos={c.lidos} novos={c.novos} falhas={c.falhas} conferida={r.conferida} "
              f"classificados={r.classificacao.resolvidos} sugestoes={r.classificacao.sugestoes} compromissos={r.compromissos.gerados}")
        if c.sync_problemas:
            print(f"ATENÇÃO sincronização: {c.sync_problemas}")
        return 0
    except RodadaEmAndamento as e:
        print(f"nada a fazer: {e}")
        return 0
    except ErroMcpAi as e:
        print(f"ERRO mcp.ai: {e.codigo}" + (f" — reconectar em {e.connect_url}" if e.connect_url else ""))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
