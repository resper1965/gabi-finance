"""Exportação semanal do banco, criptografada com a chave pública do Ricardo, para ele puxar para fora da VPS (G17).
Consome: backup (backup_db, testar_restauracao), rodada. Nunca deixa cópia em claro na pasta de saída."""
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from gabi.backup import TABELAS_CONTAGEM, backup_db, testar_restauracao
from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada

MANTER = 8


def exportar(con, destino_dir: Path, chave_publica: Path, hoje: date, manter: int = MANTER) -> Path:
    chave_publica, destino_dir = Path(chave_publica), Path(destino_dir)
    if not chave_publica.is_file():
        raise FileNotFoundError(f"chave pública ausente: {chave_publica}")
    final = destino_dir / f"gabi-brain-{hoje.isoformat()}.sqlite.gpg"
    if final.exists():
        return final  # reexecução no mesmo dia: o pacote de hoje já existe
    with registrar_rodada(con, "exportacao") as r:
        destino_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(destino_dir, 0o700)
        with tempfile.TemporaryDirectory() as tmp:  # a cópia em claro vive só aqui e some ao sair
            claro = backup_db(con, Path(tmp) / "claro", hoje)
            if not testar_restauracao(claro, TABELAS_CONTAGEM)["ok"]:
                raise RuntimeError(f"teste de restauração falhou; nada exportado: {claro}")
            parcial = final.with_name(final.name + ".parcial")
            parcial.unlink(missing_ok=True)
            try:
                gnupg = Path(tmp) / "gnupg"
                gnupg.mkdir(mode=0o700)
                p = subprocess.run(
                    ["gpg", "--homedir", str(gnupg), "--batch", "--yes", "--trust-model", "always",
                     "--recipient-file", str(chave_publica), "--output", str(parcial), "--encrypt", str(claro)],
                    capture_output=True, text=True)
                if p.returncode != 0:
                    raise RuntimeError(f"gpg falhou: {p.stderr.strip()[-200:]}")
                os.chmod(parcial, 0o600)
                parcial.rename(final)
            finally:
                parcial.unlink(missing_ok=True)
        r.lidos = 1
    for velho in sorted(destino_dir.glob("gabi-brain-*.sqlite.gpg"))[:-manter]:
        velho.unlink()
    return final


def main(banco: Path, destino_dir: Path, chave_publica: Path, hoje: date | None = None) -> int:
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    try:
        print(f"exportação: {exportar(con, destino_dir, chave_publica, hoje or date.today())}")
    except (RuntimeError, FileNotFoundError, FileExistsError) as e:
        print(f"exportação FALHOU: {e}")
        return 1
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--destino", default="/var/backups/gabi-brain/exportacao")
    ap.add_argument("--chave", default="/etc/gabi/backup.pub")
    a = ap.parse_args()
    sys.exit(main(Path(a.banco), Path(a.destino), Path(a.chave)))
