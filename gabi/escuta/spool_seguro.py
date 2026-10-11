"""Acesso a anexos do spool sem confiar no ouvinte. O spool é gravável pelo ouvinte (grupo, 2770, sem sticky): ele pode renomear
`anexos/` e plantar um symlink a qualquer instante. Por isso NADA aqui decide por caminho e usa depois: o caminho guardado tem de
ser EXATAMENTE `<spool>/anexos/<nome simples>`; abre-se `anexos` com O_DIRECTORY|O_NOFOLLOW a partir de um fd do spool e tudo
(abrir, apagar) é feito com dir_fd, que continua apontando para a pasta original mesmo que o nome seja trocado."""
import os
import stat
from pathlib import Path

_FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class AnexoGrande(RuntimeError):
    """Anexo acima do teto: nunca poderá ser processado (a rodada marca `falhou`, avisa e apaga o arquivo)."""


def _gancho() -> None:
    """Ponto de teste: roda depois de `anexos` aberto e antes de tocar no arquivo (simula a troca do ouvinte)."""


def nome_simples(nome: str) -> bool:
    return bool(nome) and nome not in (".", "..") and nome == Path(nome).name and "\\" not in nome and "\0" not in nome


def caminho_valido(spool, anexo_caminho) -> bool:
    """True se `anexo_caminho` é exatamente <spool>/anexos/<nome simples> (sem resolver nada, sem tocar no disco)."""
    try:
        p = Path(anexo_caminho)
        return spool is not None and bool(str(anexo_caminho)) and p.parent == Path(spool) / "anexos" and nome_simples(p.name)
    except (TypeError, ValueError):
        return False


def _abrir_anexos(spool, anexo_caminho) -> tuple[int, str]:
    """(fd da pasta anexos, nome). RuntimeError se o caminho não for o esperado; OSError se a pasta não abrir (symlink etc.)."""
    if not caminho_valido(spool, anexo_caminho):
        raise RuntimeError("anexo fora do spool")
    nome = Path(anexo_caminho).name
    sfd = os.open(spool, _FLAGS_DIR)
    try:
        return os.open("anexos", _FLAGS_DIR, dir_fd=sfd), nome
    finally:
        os.close(sfd)


def abrir_anexo(spool, anexo_caminho, max_bytes: int | None = None) -> tuple[bytes, str]:
    """Lê o anexo: só arquivo regular (O_NOFOLLOW; FIFO não bloqueia), tamanho checado no fd antes de ler e leitura limitada a
    max_bytes+1. Devolve (bytes, nome). AnexoGrande (RuntimeError): acima do teto. RuntimeError: caminho inesperado ou não regular.
    OSError: não abriu."""
    dfd, nome = _abrir_anexos(spool, anexo_caminho)
    fd = -1
    try:
        _gancho()
        fd = os.open(nome, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dfd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError("anexo não é arquivo regular")
        if max_bytes is not None and st.st_size > max_bytes:
            raise AnexoGrande("anexo maior que o teto")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            if max_bytes is None:
                return f.read(), nome
            dados = f.read(max_bytes + 1)  # leitura limitada: o arquivo pode crescer depois do fstat (M8)
        if len(dados) > max_bytes:
            raise AnexoGrande("anexo maior que o teto")
        return dados, nome
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(dfd)


def apagar_anexo(spool, anexo_caminho) -> bool:
    """Apaga o anexo (unlink com dir_fd). False se o caminho não for o esperado, se não existir ou se qualquer passo falhar."""
    try:
        dfd, nome = _abrir_anexos(spool, anexo_caminho)
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        _gancho()
        os.unlink(nome, dir_fd=dfd)
        return True
    except OSError:
        return False
    finally:
        os.close(dfd)
