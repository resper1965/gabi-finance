"""Backup do banco com integrity_check e teste de restauração (spec §13.3). Consome: db, rodada."""
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada
from gabi.hoje import hoje_brt

TABELAS_CONTAGEM = ["pessoa", "empresa", "compromisso", "fatura", "memoria", "acesso", "decisao",
                    "compromisso_linha", "valor_do_mes"]


def backup_db(con: sqlite3.Connection, destino_dir: Path, hoje: date) -> Path:
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destino_dir, 0o700)
    final = destino_dir / f"gabi-brain-{hoje.isoformat()}.sqlite"
    parcial = final.with_name(final.name + ".parcial")
    if final.exists():
        raise FileExistsError(f"já existe backup de {hoje}: {final}")
    parcial.unlink(missing_ok=True)
    antiga = os.umask(0o077)
    try:
        dst = sqlite3.connect(parcial)
        try:
            con.backup(dst)
            dst.execute("pragma journal_mode=delete")  # sem -wal/-shm ao lado do arquivo
            if dst.execute("pragma integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup falhou no integrity_check")
        finally:
            dst.close()
        os.chmod(parcial, 0o600)
        parcial.rename(final)
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    finally:
        os.umask(antiga)
    return final


def testar_restauracao(arquivo: Path, tabelas: list[str]) -> dict:
    """Restaura numa cópia temporária, confere integridade e conta linhas. Nunca altera o arquivo original."""
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "restaurado.sqlite"
        shutil.copy2(arquivo, copia)
        try:
            con = sqlite3.connect(copia)
            try:
                if con.execute("pragma integrity_check").fetchone()[0] != "ok":
                    return {"ok": False, "contagens": {}}
                existentes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
                return {"ok": True, "contagens": {
                    t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tabelas if t in existentes}}
            finally:
                con.close()
        except sqlite3.DatabaseError:
            return {"ok": False, "contagens": {}}


def main(banco: Path, destino_dir: Path, hoje: date | None = None, testar: bool = False) -> int:
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    hoje = hoje or hoje_brt()
    if (Path(destino_dir) / f"gabi-brain-{hoje.isoformat()}.sqlite").exists():
        print(f"backup de {hoje} já existe; nada a fazer")  # reexecução no mesmo dia (instalação) não é falha
        return 0
    try:
        with registrar_rodada(con, "backup") as r:
            arq = backup_db(con, destino_dir, hoje)
            r.lidos = 1
            if testar:
                res = testar_restauracao(arq, TABELAS_CONTAGEM)
                if not res["ok"]:
                    raise RuntimeError(f"teste de restauração falhou: {arq}")
                print("restauração testada:", res["contagens"])
            print(f"backup: {arq}")
    except (RuntimeError, FileExistsError) as e:
        print(f"backup FALHOU: {e}")
        return 1
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--destino", default="/var/backups/gabi-brain")
    ap.add_argument("--testar", action="store_true", help="roda o teste de restauração (mensal)")
    a = ap.parse_args()
    sys.exit(main(Path(a.banco), Path(a.destino), testar=a.testar))
