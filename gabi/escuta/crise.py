"""Palavras de risco da escuta. A lista é DADO (tabela parametro, chave escuta.palavras_risco, JSON), nunca código."""
import json
import re
import unicodedata

CHAVE = "escuta.palavras_risco"


def _norm(s: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"\w+", sem.casefold()))


def palavras_risco(con) -> list[str]:
    linha = con.execute("select valor from parametro where chave=?", (CHAVE,)).fetchone()
    if linha is None:
        return []
    try:
        lista = json.loads(linha[0])
    except (ValueError, TypeError):
        return []
    return [p for p in lista if isinstance(p, str)] if isinstance(lista, list) else []


def tem_risco(texto: str, palavras: list[str]) -> bool:
    """Sem acento, sem caixa, palavra inteira (aceita expressão de várias palavras)."""
    alvo = f" {_norm(texto or '')} "
    return any((n := _norm(p)) and f" {n} " in alvo for p in palavras)


ARQUIVO_PALAVRAS = "palavras-risco.json"


def escrever_palavras_risco(con, spool) -> bool:
    """Publica a lista para o ouvinte (que não tem acesso ao banco): `<spool>/palavras-risco.json`, atômico, 0640 (o grupo do
    spool lê). Só regrava se o conteúdo mudou. True se gravou. Erro de E/S propaga (o chamador decide).
    O ouvinte escreve nesta pasta: o tmp tem nome aleatório e abre com O_EXCL|O_NOFOLLOW (nunca escreve através de symlink
    plantado), a leitura do atual não segue symlink nem abre FIFO."""
    import os
    import secrets
    from pathlib import Path
    from gabi.escuta.caixa import ler_regular
    pasta = Path(spool)
    alvo = pasta / ARQUIVO_PALAVRAS
    novo = json.dumps(palavras_risco(con), ensure_ascii=False).encode("utf-8")
    try:
        if ler_regular(alvo, 1024 * 1024) == novo:
            return False
    except (OSError, ValueError):
        pass
    tmp = pasta / f"{ARQUIVO_PALAVRAS}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
    try:
        try:
            os.fchmod(fd, 0o640)  # o umask 0077 do brain não pode esconder o arquivo do ouvinte
            os.write(fd, novo)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, alvo)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True
