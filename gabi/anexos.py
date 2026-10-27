"""Anexos (ADR-034): copia imagem e áudio do cache do Hermes para o disco do brain e os registra na caixa de entrada (`anexo` sem projeto).

Tipo pela extensão; dedupe por sha256 (o mesmo arquivo no WhatsApp e no Telegram vira um anexo); arquivo modificado há menos de 20 s espera a próxima rodada;
acima de 50 MB é ignorado. Guardado para sempre, sem mascarar: diretório 0700, arquivo 0600. O log só imprime contagens, nunca nome nem conteúdo.
Consome: db (anexo). A transcrição de áudio (`gabi.transcricao`, opcional) entra como o callable `transcrever`."""
import argparse
import datetime as dt
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

from gabi.db import conectar, migrar

UTC = dt.timezone.utc
LIMITE_BYTES = 50 * 1024 * 1024
ESPERA_S = 20
IMAGENS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
AUDIOS = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac"}
ORIGENS_PADRAO = (Path.home() / ".hermes/cache/images", Path.home() / ".hermes/cache/audio")
DESTINO_PADRAO = Path("/var/lib/gabi-brain/anexos")


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _guardar(origem: Path, destino: Path, sha: str, ext: str) -> str:
    """Copia (não move) para destino/<sha[:2]>/<sha><ext> com 0700 e 0600; devolve o caminho relativo."""
    destino.mkdir(parents=True, exist_ok=True)
    destino.chmod(0o700)
    pasta = destino / sha[:2]
    pasta.mkdir(exist_ok=True)
    pasta.chmod(0o700)
    final = pasta / f"{sha}{ext}"
    tmp = pasta / f".{sha}{ext}.tmp"
    shutil.copyfile(origem, tmp)
    tmp.chmod(0o600)
    os.replace(tmp, final)
    return f"{sha[:2]}/{sha}{ext}"


def coletar(con, agora: dt.datetime, origens: list[Path], destino: Path, transcrever: Callable[[Path], str | None] | None = None,
            limite_bytes: int = LIMITE_BYTES) -> dict:
    """-> {"novos", "repetidos", "ignorados", "adiados"}. Exceção do transcritor vira transcrição nula e nunca derruba a rodada."""
    cont = {"novos": 0, "repetidos": 0, "ignorados": 0, "adiados": 0}
    for pasta in origens:
        try:
            arquivos = sorted(pasta.iterdir())
        except OSError:
            continue
        for arq in arquivos:
            if not arq.is_file():  # subpasta: não é anexo, nem conta
                continue
            ext = arq.suffix.lower()
            tipo = "imagem" if ext in IMAGENS else "audio" if ext in AUDIOS else None
            try:
                if tipo is None:
                    cont["ignorados"] += 1
                    continue
                st = arq.stat()
                if st.st_size > limite_bytes:
                    cont["ignorados"] += 1
                    continue
                if agora.timestamp() - st.st_mtime < ESPERA_S:
                    cont["adiados"] += 1
                    continue
                sha = _sha256(arq)
                if con.execute("select 1 from anexo where sha256=?", (sha,)).fetchone():
                    cont["repetidos"] += 1
                    continue
                rel = _guardar(arq, destino, sha, ext)
            except OSError:
                cont["ignorados"] += 1
                continue
            texto = None
            if transcrever is not None and tipo == "audio":
                try:
                    texto = transcrever(destino / rel) or None
                except Exception:
                    texto = None
            con.execute("insert into anexo(tipo, arquivo, sha256, transcricao, recebido_em) values (?,?,?,?,?)",
                        (tipo, rel, sha, texto, dt.datetime.fromtimestamp(st.st_mtime, UTC).isoformat()))
            cont["novos"] += 1
    return cont


def _agora() -> dt.datetime:
    return dt.datetime.now(UTC)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    a = ap.parse_args(argv)
    origens = [Path(p) for p in os.environ["ANEXOS_ORIGENS"].split(os.pathsep) if p] if os.environ.get("ANEXOS_ORIGENS") else list(ORIGENS_PADRAO)
    destino = Path(os.environ.get("ANEXOS_DIR") or DESTINO_PADRAO)
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    r = coletar(con, _agora(), origens, destino)
    print(f"anexos: novos={r['novos']} repetidos={r['repetidos']} ignorados={r['ignorados']} adiados={r['adiados']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
