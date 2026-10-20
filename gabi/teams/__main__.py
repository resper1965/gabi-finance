"""Programa do Teams (timer): coleta metadados das conversas das contas liberadas (`teams_fonte.estado='sim'`) pela ponte e imprime SÓ contagens.
Este processo não tem rede nem segredo (o Graph vive no serviço de fontes, GABI_FONTES_SOCKET). Nunca imprime nome nem texto.
Sai 0 se ao menos uma conta coletou ou não há conta liberada; 1 só se todas falham. Uso: python -m gabi.teams"""
import datetime as dt
import os
import sys
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada
from gabi.teams.coletar import coletar


def main(banco: Path | None = None, *, ponte=None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    if ponte is None:
        sock = os.environ.get("GABI_FONTES_SOCKET")
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.ponte import PonteGraph
        ponte = PonteGraph(sock)
        if not ponte.configurada():
            print("ERRO: o Graph da ness não está configurado no serviço de fontes", file=sys.stderr)
            return 2
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        with registrar_rodada(con, "teams") as rod:  # rodada ok mesmo sem conta liberada
            r = coletar(con, ponte, dt.datetime.now(dt.timezone.utc))
            rod.lidos = sum(v.get("chats", 0) for v in r.values())
            rod.novos = sum(v.get("novas", 0) for v in r.values())
            falhas = sum(1 for v in r.values() if "erro" in v)
            if r and falhas == len(r):
                rod.falha = f"todas as {len(r)} conta(s) falharam"
            elif falhas:
                rod.aviso = f"{falhas} conta(s) com falha"
    finally:
        con.close()
    ok = [v for v in r.values() if "erro" not in v]
    print(f"teams: contas={len(r)} ok={len(ok)} chats={sum(v['chats'] for v in ok)} novas={sum(v['novas'] for v in ok)} puladas={sum(v.get('puladas', 0) for v in ok)}")
    for conta, v in r.items():
        if "erro" in v:
            print(f"AVISO: conta {conta} falhou: {v['erro']}", file=sys.stderr)
    return 1 if r and not ok else 0


if __name__ == "__main__":
    sys.exit(main())
