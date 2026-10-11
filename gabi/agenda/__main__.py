"""Programa da agenda (timer de 15 min): sincroniza as fontes liberadas (`agenda_fonte.estado='sim'`) pela ponte e imprime SÓ contagens.
O Google chega pela ponte do serviço de fontes (GABI_FONTES_SOCKET); este processo não tem rede nem segredo. Nunca imprime título de evento.
Sai 0 se ao menos uma fonte sincronizou ou não há fonte liberada; 1 só se todas falham e alguma por motivo diferente de "conta não autorizada".
Uso: python -m gabi.agenda"""
import datetime as dt
import os
import sys
from pathlib import Path

from gabi.agenda.sincronizar import sincronizar
from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada


def main(banco: Path | None = None, *, listar=None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    if listar is None:
        sock = os.environ.get("GABI_FONTES_SOCKET")
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.ponte import PonteAgenda
        ponte = PonteAgenda(sock)
        if not ponte.configurada():
            print("ERRO: agenda do Google não configurada no serviço de fontes", file=sys.stderr)
            return 2
        listar = ponte.listar_eventos
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        with registrar_rodada(con, "agenda") as rod:  # alimenta o frescor do envelope; rodada ok sem fonte liberada
            r = sincronizar(con, listar, dt.datetime.now(dt.timezone.utc).isoformat())
            rod.lidos = sum(v.get("lidos", 0) for v in r.values())
            rod.novos = sum(v.get("gravados", 0) for v in r.values())
            falhas = sum(1 for v in r.values() if "erro" in v)
            if r and falhas == len(r):  # nenhuma fonte lida: não vale como "dados frescos"
                rod.falha = f"todas as {len(r)} fonte(s) falharam"
            elif falhas:
                rod.aviso = f"{falhas} fonte(s) com falha"
        contas = {x["id"]: x["conta"] for x in con.execute("select id, conta from agenda_fonte")}
    finally:
        con.close()
    ok = {k: v for k, v in r.items() if "erro" not in v}
    erros = {k: v["erro"] for k, v in r.items() if "erro" in v}
    for fid, v in ok.items():
        print(f"agenda: fonte={fid} lidos={v['lidos']} gravados={v['gravados']} apagados={v['apagados']} pulados={v['pulados']} recarga={'sim' if v['recarga'] else 'nao'}")
    print(f"agenda: fontes={len(r)} ok={len(ok)}")
    for fid, msg in erros.items():
        print(f"AVISO: fonte {contas.get(fid, fid)} falhou: {msg}", file=sys.stderr)
    todas = bool(r) and not ok
    inesperado = any(not m.startswith("conta não autorizada") for m in erros.values())
    return 1 if todas and inesperado else 0


if __name__ == "__main__":
    sys.exit(main())
