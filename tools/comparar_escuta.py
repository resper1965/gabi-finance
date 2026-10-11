"""Compara, na fase paralela, o que a escuta NOVA classificou (escuta_msg, modo registro) com o que o agente `escuta` do OpenClaw
registrou (fila do reembolso). Somente leitura dos dois lados. Só conta: chave = (remetente, tipo, dia em Brasília).
A saída não tem texto de mensagem nem número completo (+55119****5678).

Formato do lado antigo (derivado de escuta.py, só o código): `pista-*.json` (saúde: campos quem, criado_em), `aviso-*.json`
(texto do aviso: "💸 Pedido de QUEM — ..." = pedido; "🚨 NIVEL: QUEM — ..." = crise), na raiz e em `feitas/`. O agente antigo só
guarda o NOME do contato (ou +número quando desconhecido): o nome é resolvido para número por escuta_remetente.nome; nome sem
número conhecido aparece como remetente "?". Qualquer outro arquivo (cmd-*, JSON inválido, texto fora do padrão) é pulado e contado em `ilegiveis`.

Uso: python -m tools.comparar_escuta [--banco ...] [--fila-antiga ...] [--escuta-py ...] [--desde AAAA-MM-DD]
Saída 0 só quando não há divergência; 1 com divergência; 2 se não deu para ler."""
import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from gabi.escuta.caixa import normalizar_telefone

BRT = ZoneInfo("America/Sao_Paulo")
TIPOS = ("pedido", "saude", "crise")
_PEDIDO = re.compile(r"^💸 Pedido de (?P<quem>.+?)(?: — |$)")
_CRISE = re.compile(r"^🚨 (?:vida|saude|seguranca): (?P<quem>.+?) — ")
_CHAVES_TEXTO = ("texto", "mensagem", "msg", "aviso", "text")
_CHAVES_DATA = ("criado_em", "enfileirado_em", "em", "data", "ts")


@dataclass
class Resultado:
    divergencias: list = field(default_factory=list)
    ilegiveis: int = 0
    chaves: int = 0


def mascarar(numero: str | None) -> str:
    d = numero if isinstance(numero, str) else ""
    return d[:6] + "****" + d[-4:] if len(d) >= 12 else "?"


def abrir_somente_leitura(banco: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(banco).resolve()}?mode=ro", uri=True)


def _dia_brt(valor: str) -> str | None:
    try:
        t = dt.datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    t = t.replace(tzinfo=BRT) if t.tzinfo is None else t.astimezone(BRT)  # sem fuso = Brasília
    return t.date().isoformat()


def _lado_brain(con, desde: str | None) -> dict:
    out: dict = {}
    for de, quando, tipo in con.execute(
            "select de, recebida_em, tipo from escuta_msg where tipo in ('pedido','saude','crise')"):
        dia = _dia_brt(quando)
        num = normalizar_telefone(de)
        if dia and num and (not desde or dia >= desde):
            out.setdefault((num, dia), set()).add(tipo)
    return out


def _nomes(con) -> dict:
    return {(n or "").strip().casefold(): num for num, n in con.execute(
        "select numero, nome from escuta_remetente where nome is not null and nome <> ''") if (n or "").strip()}


def _classificar_aviso(dados) -> tuple[str, str] | None:
    if not isinstance(dados, dict):
        return None
    texto = next((dados[k] for k in _CHAVES_TEXTO if isinstance(dados.get(k), str)), None)
    if not texto:
        return None
    for rx, tipo in ((_PEDIDO, "pedido"), (_CRISE, "crise")):
        m = rx.match(texto.strip())
        if m:
            return tipo, m.group("quem").strip()
    return None


def _lado_agente(fila: Path, nomes: dict, desde: str | None, res: Resultado) -> dict:
    out: dict = {}
    arquivos = [p for sub in (fila, fila / "feitas") if sub.is_dir() for p in sorted(sub.iterdir())
                if p.is_file() and p.suffix == ".json" and p.name.split("-")[0] in ("aviso", "pista", "cmd")]
    for p in arquivos:
        try:
            dados = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            res.ilegiveis += 1
            continue
        if p.name.startswith("pista-") and isinstance(dados, dict) and isinstance(dados.get("quem"), str):
            tipo, quem = "saude", dados["quem"].strip()
        elif p.name.startswith("aviso-") and (c := _classificar_aviso(dados)):
            tipo, quem = c
        else:
            res.ilegiveis += 1
            continue
        quando = next((dados[k] for k in _CHAVES_DATA if isinstance(dados.get(k), str)), None)
        dia = _dia_brt(quando) if quando else dt.datetime.fromtimestamp(p.stat().st_mtime, BRT).date().isoformat()
        if not dia:
            res.ilegiveis += 1
            continue
        num = normalizar_telefone(quem) if quem.startswith("+") else nomes.get(quem.casefold())
        if not desde or dia >= desde:
            out.setdefault((num, dia), set()).add(tipo)
    return out


def comparar(con, fila: Path, desde: str | None = None) -> Resultado:
    res = Resultado()
    brain = _lado_brain(con, desde)
    agente = _lado_agente(Path(fila), _nomes(con), desde, res)
    for chave in sorted(set(brain) | set(agente), key=lambda k: (k[1], k[0] or "")):
        b, a = brain.get(chave, set()), agente.get(chave, set())
        res.chaves += 1
        solo_b, solo_a = b - a, a - b
        base = {"remetente": mascarar(chave[0]), "dia": chave[1]}
        if solo_b and solo_a:
            res.divergencias.append({**base, "divergencia": "tipo_diferente", "brain": sorted(b), "agente": sorted(a)})
        else:
            res.divergencias += [{**base, "divergencia": "so_no_brain", "tipo": t} for t in sorted(solo_b)]
            res.divergencias += [{**base, "divergencia": "so_no_agente", "tipo": t} for t in sorted(solo_a)]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="comparar_escuta")
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--fila-antiga", default="/var/lib/gabi/.openclaw/fila-reembolso")
    ap.add_argument("--escuta-py", default="/var/lib/gabi/.openclaw/scripts/escuta.py")
    ap.add_argument("--desde", help="AAAA-MM-DD (dia em Brasília)")
    a = ap.parse_args(argv)
    if a.desde and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.desde):
        print("comparar_escuta: --desde deve ser AAAA-MM-DD")
        return 2
    fila = Path(a.fila_antiga)
    if not fila.is_dir():
        print("comparar_escuta: fila do agente antigo não encontrada ou sem permissão de leitura")
        return 2
    try:
        existe = Path(a.escuta_py).exists()
    except OSError:
        existe = False
    if not existe:
        print("comparar_escuta: aviso: escuta.py antigo não encontrado (o formato lido é o documentado neste módulo)", file=sys.stderr)
    try:
        con = abrir_somente_leitura(Path(a.banco))
        try:
            res = comparar(con, fila, a.desde)
        finally:
            con.close()
    except (sqlite3.Error, OSError) as e:
        print(f"comparar_escuta: não consegui ler os dados: {type(e).__name__}")
        return 2
    for d in res.divergencias:
        print(json.dumps(d, ensure_ascii=False))
    cont = {k: sum(d["divergencia"] == k for d in res.divergencias) for k in ("so_no_brain", "so_no_agente", "tipo_diferente")}
    print(f"comparar_escuta: total={len(res.divergencias)} " + " ".join(f"{k}={v}" for k, v in cont.items())
          + f" ilegiveis={res.ilegiveis} remetente_dia={res.chaves}")
    return 1 if res.divergencias else 0


if __name__ == "__main__":
    sys.exit(main())
