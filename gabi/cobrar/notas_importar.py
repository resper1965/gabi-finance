"""Importa as NFS-e do Nibo para `nota_fiscal` e guarda PDF/XML em /var/lib/gabi-brain/notas.
Uso: python -m gabi.cobrar.notas_importar [--desde AAAA-MM-DD]. O Nibo é lido pela ponte (GABI_FONTES_SOCKET): este processo não tem o token (R5).
Consome: cobrar.notas, rodada, fontes.ambiente."""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from gabi.cobrar.notas import importar
from gabi.db import conectar, migrar
from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.nibo import ErroNibo
from gabi.rodada import registrar_rodada


def main(banco: Path, pasta: Path, desde: dt.date, nibo=None) -> int:
    nibo = nibo or fontes_do_ambiente()["nibo"]()
    if nibo is None:
        print("ERRO: Nibo não configurado no serviço de fontes")
        return 1
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        with registrar_rodada(con, "notas-nibo") as r:
            creditos = {c["scheduleId"]: c for c in nibo.agendamentos_a_receber()}
            resumo = importar(con, nibo.nfse(desde), creditos, nibo.obter_arquivo, pasta, dt.datetime.now(dt.timezone.utc))
            r.lidos, r.novos, r.alterados = resumo.lidas, resumo.novas, resumo.alteradas
            if resumo.falhas:
                r.aviso = f"{len(resumo.falhas)} arquivo(s) não baixado(s): " + "; ".join(resumo.falhas[:5])
    except ErroNibo as e:
        print(f"ERRO Nibo: {e}")
        return 1
    print(f"notas: lidas={resumo.lidas} novas={resumo.novas} alteradas={resumo.alteradas} arquivos={resumo.arquivos} falhas={len(resumo.falhas)}")
    for f in resumo.falhas[:10]:
        print("  falha:", f)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    ap.add_argument("--pasta", default="/var/lib/gabi-brain/notas")
    ap.add_argument("--desde", default="2017-01-01")
    a = ap.parse_args()
    sys.exit(main(Path(a.banco), Path(a.pasta), dt.date.fromisoformat(a.desde)))
