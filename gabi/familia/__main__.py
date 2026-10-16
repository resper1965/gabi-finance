"""Programa dos exames (timer de 30 min): `rodar` da rodada_exames. Imprime SÓ contagens, nunca nome, marcador ou valor (ADR-014).
O Paperless e o modelo chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); a chave do cofre vem de GABI_SAUDE_CHAVE_ARQUIVO (R5).
Sem a chave do cofre: não roda e grava o aviso `servico_falhou`. Uso: python -m gabi.familia"""
import datetime as dt
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.avisos import registrar_servico_falhou
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.escuta.__main__ import ModeloComCusto, cliente_da_ponte
from gabi.familia.ambiente import saude_do_ambiente
from gabi.familia.rodada_exames import rodar
from gabi.familia.saude import abrir_saude
from gabi.fontes.ponte import Ponte
from gabi.rodada import registrar_rodada

BRT = ZoneInfo("America/Sao_Paulo")
UNIDADE = "gabi-brain-exames.service"
_AUTO = object()


def main(banco: Path | None = None, *, paperless=None, cliente=_AUTO, cofre=_AUTO, agora: dt.datetime | None = None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    agora = agora or dt.datetime.now(dt.timezone.utc)
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    if cofre is _AUTO:
        cofre = saude_do_ambiente(banco.parent)
    if cofre is None:
        registrar_servico_falhou(con, UNIDADE, agora)
        print("ERRO: a chave do cofre de saúde não está configurada", file=sys.stderr)
        return 1
    sock = os.environ.get("GABI_FONTES_SOCKET")
    if paperless is None:
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        paperless = Ponte(sock, "paperless")
    if cliente is _AUTO:
        cliente = cliente_da_ponte(sock)
        if cliente is not None:
            cliente = ModeloComCusto(cliente, banco, tarefa="exames")
    try:
        with registrar_rodada(con, "exames") as rod:
            r = rodar(con, lambda: abrir_saude(*cofre), paperless, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()),
                      agora.astimezone(dt.timezone.utc).isoformat())
            rod.lidos, rod.novos = r["novos"], r["extraidos"]
            if r["falhos"]:
                rod.aviso = f"{r['falhos']} documento(s) de exame falharam"
    finally:
        if isinstance(cliente, ModeloComCusto):
            cliente.fechar()
        con.close()
    print("exames: " + " ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
