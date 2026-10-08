"""Arquivo bruto imutável: JSONL comprimido por dia e fonte, base para reconstruir o banco (spec §13.2)."""
import gzip
import json
import os
from datetime import date
from pathlib import Path
from typing import Iterable


def gravar_bruto(base: Path, fonte: str, dia: date, linhas: Iterable[dict]) -> Path:
    destino = Path(base) / fonte / f"{dia:%Y}" / f"{dia:%m}" / f"{dia:%d}.jsonl.gz"
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    if destino.exists():
        raise FileExistsError(f"bruto já existe e é imutável: {destino}")
    fd = os.open(parcial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb") as gz:
            for linha in linhas:
                gz.write((json.dumps(linha, ensure_ascii=False) + "\n").encode("utf-8"))
        os.link(parcial, destino)  # falha se o destino surgiu no meio: nunca sobrescreve
    finally:
        parcial.unlink(missing_ok=True)
    return destino
