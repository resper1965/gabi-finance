"""Job da rodada do Trabalho (timer): `python -m gabi.trabalho`. Credenciais só do ambiente (/etc/gabi/trabalho.env, colocado pelo Ricardo; R5)."""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.fontes.tokens import cliente_do_ambiente
from gabi.trabalho.rodada_trabalho import rodar


def main(banco: Path, cliente_de=None) -> int:
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    r = rodar(con, cliente_de or cliente_do_ambiente(), dt.datetime.now(dt.timezone.utc))
    print(f"trabalho: caixas={r.caixas} mensagens={r.mensagens} eventos={r.eventos} tarefas={r.tarefas} falhas={r.falhas}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sys.exit(main(Path(ap.parse_args().banco)))
