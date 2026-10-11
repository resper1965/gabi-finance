"""Caixa de entrada da escuta: lê o spool (um JSON por mensagem) e grava em escuta_msg."""
import datetime as dt
import fnmatch
import json
import os
import re
import stat
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.db import transacao

BRT = ZoneInfo("America/Sao_Paulo")


def normalizar_telefone(bruto: str) -> str | None:
    """E.164 brasileiro (+55...). Sem DDI assume +55. None se inválido."""
    if not isinstance(bruto, str):
        return None
    digitos = re.sub(r"\D", "", bruto.split("@")[0])
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return "+" + digitos
    return None


def registrar_remetente_visto(con, numero: str, agora: str) -> None:
    """Cria 'pendente' se não existe; sempre conta; nunca reabre ignorado/bloqueado."""
    con.execute(
        "insert into escuta_remetente(numero, estado, vista_em, qtd) values (?, 'pendente', ?, 1) "
        "on conflict(numero) do update set qtd = qtd + 1, vista_em = excluded.vista_em",
        (numero, agora))


LIMITE_JSON = 5 * 1024 * 1024  # uma mensagem de texto não chega perto; acima disso é lixo ou ataque


def ler_regular(caminho, limite: int, dir_fd: int | None = None) -> bytes:
    """O spool é gravável pelo ouvinte (não confiável): só lê arquivo REGULAR, sem seguir symlink (O_NOFOLLOW) e sem bloquear
    em FIFO (O_NONBLOCK; o tipo é checado no fd aberto). OSError/ValueError se for outra coisa ou passar de `limite`."""
    fd = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limite:
            raise ValueError("não é arquivo regular ou é grande demais")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            return f.read(limite + 1)[:limite]
    finally:
        if fd >= 0:
            os.close(fd)


_FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _mover(spool_fd: int, nome: str, sub: str) -> None:
    """Move `nome` (entrada direta do spool) para `sub` (lidos/invalidos) ANCORADO no fd do spool: a subpasta é aberta com
    O_NOFOLLOW relativo ao fd e o rename usa os dois fds, então trocar `lidos` por symlink (o ouvinte pode, o spool é 2770 sem
    sticky) não leva o arquivo para fora. Se a subpasta não abrir (symlink, não é pasta), apaga o arquivo em vez de mover."""
    dest = -1
    try:
        try:
            os.mkdir(sub, 0o2770, dir_fd=spool_fd)
        except FileExistsError:
            pass
        dest = os.open(sub, _FLAGS_DIR, dir_fd=spool_fd)
        os.rename(nome, nome, src_dir_fd=spool_fd, dst_dir_fd=dest)
        return
    except OSError:
        pass
    finally:
        if dest >= 0:
            os.close(dest)
    try:
        os.unlink(nome, dir_fd=spool_fd)
    except OSError:
        pass


def _utc(quando: str) -> str:
    """recebida_em em UTC ISO (`+00:00`). Offset explícito (`Z`, `-03:00`) é convertido; valor SEM offset é hora de Brasília. ValueError se inválido."""
    d = dt.datetime.fromisoformat(quando)
    if d.tzinfo is None:
        d = d.replace(tzinfo=BRT)
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def _ler(nome: str, sfd: int) -> dict:
    d = json.loads(ler_regular(nome, LIMITE_JSON, dir_fd=sfd).decode("utf-8"))
    if not isinstance(d, dict):
        raise ValueError("spool não é objeto")
    for k in ("id_externo", "de", "recebida_em"):
        if not isinstance(d.get(k), str) or not d[k]:
            raise ValueError(f"campo ausente: {k}")
    for k in ("texto", "id_grupo", "anexo"):
        if d.get(k) is not None and not isinstance(d[k], str):
            raise ValueError(f"tipo inválido: {k}")
    d["recebida_em"] = _utc(d["recebida_em"])
    anexo = d.get("anexo")
    if anexo is not None and (anexo in ("", ".", "..") or anexo != Path(anexo).name or "\\" in anexo):
        raise ValueError("anexo inválido")
    return d


def ingerir_spool(con, pasta: Path, agora: str) -> int:
    pasta = Path(pasta)
    try:
        sfd = os.open(pasta, _FLAGS_DIR)
    except OSError:
        return 0
    try:
        return _ingerir(con, pasta, sfd, agora)
    finally:
        os.close(sfd)


def _ingerir(con, pasta: Path, sfd: int, agora: str) -> int:
    novas = 0
    for nome in sorted(n for n in os.listdir(sfd) if fnmatch.fnmatchcase(n, "*.json")):
        if nome == "palavras-risco.json":  # lista que o brain publica para o ouvinte, não é mensagem
            continue
        try:
            d = _ler(nome, sfd)
        except (OSError, ValueError):  # JSONDecodeError e UnicodeDecodeError são ValueError
            _mover(sfd, nome, "invalidos")
            continue
        grupo = bool(d.get("grupo"))
        numero = None if grupo else normalizar_telefone(d["de"])
        bloqueado = numero is not None and con.execute(
            "select 1 from escuta_remetente where numero=? and estado='bloqueado'", (numero,)).fetchone()
        if not bloqueado:
            anexo = d.get("anexo")
            caminho = str(pasta / "anexos" / anexo) if anexo else None
            with transacao(con):
                cur = con.execute(
                    "insert or ignore into escuta_msg(id_externo, de, grupo, id_grupo, recebida_em, texto, anexo_caminho) "
                    "values (?,?,?,?,?,?,?)",
                    (d["id_externo"], numero or d["de"], int(grupo), d.get("id_grupo"), d["recebida_em"], d.get("texto"), caminho))
                if numero is not None and cur.rowcount:
                    registrar_remetente_visto(con, numero, agora)
            novas += cur.rowcount
        _mover(sfd, nome, "lidos")
    return novas


def limpar_orfaos(con, spool: Path, *, idade_h: int = 24) -> int:
    """Apaga anexo do spool que nenhuma linha de escuta_msg aponta e com mais de `idade_h` h (a API só anula o ponteiro; quem apaga é este timer).
    Só arquivo regular direto em <spool>/anexos: nunca segue symlink (nem a própria pasta `anexos`, que o ouvinte pode trocar),
    nunca entra em subpasta. Devolve só a contagem."""
    import time
    pasta = Path(spool) / "anexos"
    try:
        dfd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return 0
    try:
        nomes = os.listdir(dfd)
        referenciados = {Path(r[0]).name for r in con.execute("select anexo_caminho from escuta_msg where anexo_caminho is not null")}
        limite = time.time() - idade_h * 3600
        removidos = 0
        for nome in nomes:
            try:
                st = os.stat(nome, dir_fd=dfd, follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or nome in referenciados or st.st_mtime >= limite:
                    continue
                os.unlink(nome, dir_fd=dfd)
                removidos += 1
            except OSError:
                continue
        return removidos
    finally:
        os.close(dfd)
