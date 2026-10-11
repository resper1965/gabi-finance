"""Caixa de entrada da escuta: lê o spool (um JSON por mensagem) e grava em escuta_msg."""
import datetime as dt
import json
import re
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


def _mover(arq: Path, destino: Path) -> None:
    destino.mkdir(exist_ok=True)
    arq.replace(destino / arq.name)


def _utc(quando: str) -> str:
    """recebida_em em UTC ISO (`+00:00`). Offset explícito (`Z`, `-03:00`) é convertido; valor SEM offset é hora de Brasília. ValueError se inválido."""
    d = dt.datetime.fromisoformat(quando)
    if d.tzinfo is None:
        d = d.replace(tzinfo=BRT)
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def _ler(arq: Path) -> dict:
    d = json.loads(arq.read_text(encoding="utf-8"))
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
    novas = 0
    for arq in sorted(pasta.glob("*.json")):
        try:
            d = _ler(arq)
        except (OSError, ValueError):  # JSONDecodeError e UnicodeDecodeError são ValueError
            _mover(arq, pasta / "invalidos")
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
        _mover(arq, pasta / "lidos")
    return novas


def limpar_orfaos(con, spool: Path, *, idade_h: int = 24) -> int:
    """Apaga anexo do spool que nenhuma linha de escuta_msg aponta e com mais de `idade_h` h (a API só anula o ponteiro; quem apaga é este timer).
    Só arquivo regular direto em <spool>/anexos: nunca segue symlink, nunca entra em subpasta. Devolve só a contagem."""
    import os
    import time
    pasta = Path(spool) / "anexos"
    try:
        entradas = list(os.scandir(pasta))
    except OSError:
        return 0
    referenciados = {Path(r[0]).name for r in con.execute("select anexo_caminho from escuta_msg where anexo_caminho is not null")}
    limite = time.time() - idade_h * 3600
    removidos = 0
    for e in entradas:
        try:
            if e.is_symlink() or not e.is_file(follow_symlinks=False) or e.name in referenciados:
                continue
            if e.stat(follow_symlinks=False).st_mtime >= limite:
                continue
            os.unlink(e.path)
            removidos += 1
        except OSError:
            continue
    return removidos
