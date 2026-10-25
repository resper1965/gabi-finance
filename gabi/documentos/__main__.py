"""Programa dos documentos (timer diário, 05h): lê os documentos novos ou alterados do Paperless, extrai pelo modelo só do OCR e registra
PROPOSTAS para o Ricardo aprovar. Imprime SÓ contagens. O Paperless e o modelo chegam pela ponte do serviço de fontes (GABI_FONTES_SOCKET);
este processo não tem rede nem segredo. Sai 0 em rodada normal (inclusive parada por falta de modelo ou teto); 2 sem ponte; 1 se o Paperless falha.
Uso: python -m gabi.documentos"""
import datetime as dt
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.avisos import _parametro
from gabi.correio.modelo import ModeloComCusto, cliente_da_ponte
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import orcamento_do_banco
from gabi.dinheiro.rodar import RodadaEmAndamento, _lock
from gabi.documentos.leitura import ler
from gabi.fontes.ponte import Ponte
from gabi.rodada import registrar_rodada

BRT = ZoneInfo("America/Sao_Paulo")
_AUTO = object()


def main(banco: Path | None = None, *, paperless=None, cliente=_AUTO, agora: dt.datetime | None = None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sock = os.environ.get("GABI_FONTES_SOCKET")
    if paperless is None:
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        paperless = Ponte(sock, "paperless")
        if not paperless.configurada():
            print("ERRO: Paperless não configurado no serviço de fontes", file=sys.stderr)
            return 2
    agora = agora or dt.datetime.now(dt.timezone.utc)
    if cliente is _AUTO:
        cliente = cliente_da_ponte(sock)
        if cliente is not None:
            cliente = ModeloComCusto(cliente, banco, tarefa="documentos")
    con = conectar(banco)
    try:
        migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
        try:
            with _lock(banco.parent / "locks", "documentos"):
                with registrar_rodada(con, "documentos") as rod:
                    r = ler(con, paperless, cliente, orcamento_do_banco(con, agora.astimezone(BRT).date()), agora,
                            max_por_rodada=_parametro(con, "documentos.max_por_rodada", 50),
                            max_caracteres=_parametro(con, "documentos.max_caracteres", 12000))
                    rod.lidos, rod.novos = r.lidos + r.sem_texto + r.sem_documento + r.falhas, r.propostas
                    if r.parada:
                        rod.aviso = "parada: " + r.parada
        except RodadaEmAndamento:
            print("documentos: já há uma rodada em andamento")
            return 0
        except Exception as e:  # noqa: BLE001 - só o tipo, nunca a mensagem
            print(f"ERRO: documentos falhou ({type(e).__name__})", file=sys.stderr)
            return 1
    finally:
        con.close()
        if isinstance(cliente, ModeloComCusto):
            cliente.fechar()
    print(f"documentos: lidos={r.lidos} propostas={r.propostas} sem_texto={r.sem_texto} sem_documento={r.sem_documento} falhas={r.falhas}"
          + (f" parada={r.parada}" if r.parada else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
