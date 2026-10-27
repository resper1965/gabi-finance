"""Transcrição local de áudio (ADR-034), isolada e opcional: o áudio nunca sai da VPS.

`carregar()` devolve um transcritor (`Path -> str | None`) ou `None` quando `faster_whisper` não está instalado ou a transcrição está desligada
(`TRANSCRICAO=desligada` no ambiente ou em /etc/gabi/transcricao.env). Modelo `small`, português, CPU, int8, carregado na primeira vez que houver áudio
e mantido pelo processo. Sem transcritor o áudio fica guardado com `transcricao` nula e tudo mais funciona. Consome: nada."""
import os
from pathlib import Path
from typing import Callable

ARQUIVO_ENV = Path("/etc/gabi/transcricao.env")
MODELO = "small"
CACHE_MODELO = "/var/lib/gabi-brain/modelos"


def _desligada() -> bool:
    if os.environ.get("TRANSCRICAO", "").strip().lower() == "desligada":
        return True
    try:
        linhas = ARQUIVO_ENV.read_text().splitlines()
    except OSError:
        return False
    return any(l.split("#")[0].replace(" ", "").lower() == "transcricao=desligada" for l in linhas)


def carregar() -> Callable[[Path], str | None] | None:
    if _desligada():
        return None
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    modelo = []

    def transcrever(caminho: Path) -> str | None:
        if not modelo:
            modelo.append(WhisperModel(MODELO, device="cpu", compute_type="int8", download_root=CACHE_MODELO))
        segmentos, _ = modelo[0].transcribe(str(caminho), language="pt")
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        return texto or None

    return transcrever
