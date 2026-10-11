"""Compara, na fase paralela, o que a escuta NOVA classificou (escuta_msg, modo registro) com o que o agente `escuta` do OpenClaw
registrou (fila do reembolso). Somente leitura dos dois lados. Só conta: chave = (remetente, tipo, dia em Brasília).
A saída não tem texto de mensagem nem número completo (+55119****5678).

Formato do lado antigo, o que está EVIDENCIADO no código (escuta.py e /opt/gabi-fin/avisos.py, lidos em 11/10/2026; nenhum arquivo da fila foi lido):
- `aviso-*.json` = {texto, midia, seq, criado_em} (avisos.enfileirar), criado_em ISO com fuso. Na raiz da fila (pendente) ou em `feitas/`.
  Textos de escuta.py: "💸 Pedido de NOME — ..." (pedido) e "🚨 vida|saude|seguranca: NOME — “...”" (crise; NOME é o nome em contatos.md ou +número).
- `pista-*.json` (saúde) com `quem` (NOME do contato) e `criado_em` ISO com fuso (escuta.py).
- Aviso com outro texto (o reembolso.py e o próprio escuta.py, p.ex. "requisitos inválidos", também usam a fila) vira `outros_avisos`: informativo, fora do gate.
NÃO verificado: `cmd-*.json` (nenhum código lido o escreve: conta como `ilegiveis`) e qualquer produtor da fila além de escuta.py/avisos.py.
O agente antigo guarda o NOME do contato, não o número: resolve-se por escuta_remetente.nome. Nome sem número fica com chave própria
("nome:N…"), nunca colapsa com outro; nome com mais de um número é `ambiguos`. Mensagem do brain cujo `de` não vira telefone (LID, grupo,
número curto) é `sem_numero`.
CUIDADO com o tempo: `criado_em` do lado antigo é quando o agente ENFILEIROU o arquivo, não quando a mensagem chegou; perto da meia-noite
de Brasília isso gera falso so_no_*: só julgue uma divergência olhando também os dias vizinhos. Sem criado_em o arquivo é ilegível (data de arquivo seria pior).

Uso: python -m tools.comparar_escuta [--banco ...] [--fila-antiga ...] [--escuta-py ...] [--desde AAAA-MM-DD]
Saída 0 SÓ com divergências = 0 E ilegiveis = 0 E sem_numero = 0 E ambiguos = 0; 1 caso contrário; 2 se não deu para ler."""
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


@dataclass
class Resultado:
    divergencias: list = field(default_factory=list)
    ilegiveis: int = 0
    sem_numero: int = 0
    ambiguos: int = 0
    outros_avisos: int = 0
    chaves: int = 0


def mascarar(chave: str | None) -> str:
    if not isinstance(chave, str) or not chave:
        return "?"
    if chave.startswith("nome:"):
        return "nome:" + chave[5:6].upper() + "…"
    return chave[:6] + "****" + chave[-4:] if len(chave) >= 12 else "+**"


def abrir_somente_leitura(banco: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(banco).resolve()}?mode=ro", uri=True)


def _dia_brt(valor: str) -> str | None:
    try:
        t = dt.datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    t = t.replace(tzinfo=BRT) if t.tzinfo is None else t.astimezone(BRT)  # sem fuso = Brasília
    return t.date().isoformat()


def _lado_brain(con, desde: str | None, res: Resultado) -> dict:
    out: dict = {}
    for de, quando, tipo in con.execute(
            "select de, recebida_em, tipo from escuta_msg where tipo in ('pedido','saude','crise')"):
        dia = _dia_brt(quando)
        if not dia or (desde and dia < desde):
            continue
        num = normalizar_telefone(de)
        if num is None:
            res.sem_numero += 1
        else:
            out.setdefault((num, dia), set()).add(tipo)
    return out


def _nomes(con) -> dict:
    """nome (casefold) -> conjunto de números; mais de um número = ambíguo."""
    out: dict = {}
    for num, n in con.execute("select numero, nome from escuta_remetente where nome is not null and nome <> ''"):
        if (n or "").strip():
            out.setdefault(n.strip().casefold(), set()).add(num)
    return out


def _classificar_aviso(texto: str) -> tuple[str, str] | None:
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
        if not isinstance(dados, dict) or not isinstance(dados.get("criado_em"), str):
            res.ilegiveis += 1
            continue
        if p.name.startswith("pista-") and isinstance(dados.get("quem"), str):
            tipo, quem = "saude", dados["quem"].strip()
        elif p.name.startswith("aviso-") and isinstance(dados.get("texto"), str):
            c = _classificar_aviso(dados["texto"])
            if c is None:
                res.outros_avisos += 1
                continue
            tipo, quem = c
        else:
            res.ilegiveis += 1
            continue
        dia = _dia_brt(dados["criado_em"])
        if not dia:
            res.ilegiveis += 1
            continue
        if quem.startswith("+"):
            chave = normalizar_telefone(quem) or "nome:" + quem
        else:
            numeros = nomes.get(quem.casefold(), set())
            if len(numeros) > 1:
                res.ambiguos += 1
            chave = next(iter(numeros)) if len(numeros) == 1 else "nome:" + quem.casefold()
        if not desde or dia >= desde:
            out.setdefault((chave, dia), set()).add(tipo)
    return out


def comparar(con, fila: Path, desde: str | None = None) -> Resultado:
    res = Resultado()
    brain = _lado_brain(con, desde, res)
    agente = _lado_agente(Path(fila), _nomes(con), desde, res)
    for chave in sorted(set(brain) | set(agente), key=lambda k: (k[1], k[0])):
        b, a = brain.get(chave, set()), agente.get(chave, set())
        res.chaves += 1
        solo_b, solo_a = b - a, a - b
        base = {"remetente": mascarar(chave[0]), "dia": chave[1]}
        if solo_b and solo_a:
            res.divergencias.append({**base, "divergencia": "tipo_diferente", "tipo": sorted(b | a), "brain": sorted(b), "agente": sorted(a)})
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
          + f" ilegiveis={res.ilegiveis} sem_numero={res.sem_numero} ambiguos={res.ambiguos}"
          + f" outros_avisos={res.outros_avisos} remetente_dia={res.chaves}")
    return 1 if (res.divergencias or res.ilegiveis or res.sem_numero or res.ambiguos) else 0


if __name__ == "__main__":
    sys.exit(main())
