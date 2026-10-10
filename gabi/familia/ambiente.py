"""Chave e caminho do arquivo de saúde a partir do ambiente (R5): GABI_SAUDE_CHAVE_ARQUIVO (32 bytes crus, ou 64 hex, ou base64) e GABI_SAUDE_ARQUIVO (padrão: <pasta do banco>/saude.enc)."""
import base64
import binascii
import os
from pathlib import Path


def _chave(bruto: bytes) -> bytes:
    if len(bruto) == 32:
        return bruto
    texto = bruto.strip()
    for decodificar in (bytes.fromhex, base64.b64decode):
        try:
            d = decodificar(texto.decode("ascii"))
        except (ValueError, UnicodeDecodeError, binascii.Error):
            continue
        if len(d) == 32:
            return d
    raise ValueError("a chave da saúde deve ter 32 bytes (crus, hex ou base64)")


def saude_do_ambiente(pasta_do_banco: Path, env=None) -> tuple[Path, bytes] | None:
    env = os.environ if env is None else env
    arquivo_chave = env.get("GABI_SAUDE_CHAVE_ARQUIVO")
    if not arquivo_chave or not Path(arquivo_chave).is_file():
        return None
    return Path(env.get("GABI_SAUDE_ARQUIVO") or pasta_do_banco / "saude.enc"), _chave(Path(arquivo_chave).read_bytes())
