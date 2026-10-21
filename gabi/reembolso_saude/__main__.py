"""Programa do reembolso de saúde (timer de 15 min): `rodar` da rodada e, na segunda a partir das 08h (Brasília), o aviso com a lista da semana.
Imprime SÓ contagens, nunca nome, valor ou texto (ADR-014). O Paperless e o modelo chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET); a chave do cofre
vem de GABI_SAUDE_CHAVE_ARQUIVO (R5). Um escritor do cofre por vez: trava de arquivo ao lado do cofre. Uso: python -m gabi.reembolso_saude"""
import datetime as dt
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.avisos import _novo, registrar_servico_falhou
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.correio.modelo import ModeloComCusto, cliente_da_ponte
from gabi.familia.ambiente import saude_do_ambiente
from gabi.familia.saude import abrir_saude
from gabi.fontes.ponte import Ponte
from gabi.reembolso_saude import texto
from gabi.reembolso_saude.requisitos import RequisitosInvalidos
from gabi.reembolso_saude.rodada import rodar
from gabi.rodada import registrar_rodada

BRT = ZoneInfo("America/Sao_Paulo")
UNIDADE = "gabi-brain-reembolso-saude.service"
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
            cliente = ModeloComCusto(cliente, banco, tarefa="reembolso-saude", tarefa_visao="reembolso-visao")
    try:
        try:
            with registrar_rodada(con, "reembolso-saude") as rod:
                r = rodar(con, lambda: abrir_saude(*cofre), paperless, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), agora)
                rod.lidos, rod.novos = r["novos"], r["classificados"]
                if r["falhos"]:
                    rod.aviso = f"{r['falhos']} documento(s) de reembolso falharam"
            if r["motivo_espera"]:
                _novo(con, agora, "reembolso_saude_sem_modelo", "modelo", {"motivo": r["motivo_espera"]})
            texto.avisar_semana(con, agora)
        except TimeoutError:  # a trava do cofre (gabi.familia.saude) esperou e a outra rodada não soltou
            print("reembolso-saude: cofre em uso por outra rodada; nada feito")
            return 0
        except RequisitosInvalidos:
            _novo(con, agora, "reembolso_saude_requisitos", "requisitos", {})
            print("reembolso-saude: requisitos inválidos; parado até corrigir")
            return 0
        finally:
            if isinstance(cliente, ModeloComCusto):
                cliente.fechar()
    finally:
        con.close()
    print("reembolso-saude: " + " ".join(f"{k}={v}" for k, v in r.items() if k != "motivo_espera"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
