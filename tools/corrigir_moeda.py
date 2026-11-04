"""Refaz valor_centavos, moeda, valor_original_centavos e convertido dos lançamentos a partir do bruto imutável (sem rede), com a mesma
regra da captura (gabi.dinheiro.moeda). Idempotente. --dry-run só imprime contagens. Nunca imprime descrição nem valor por lançamento.
Só toca em moeda estrangeira, usando o bruto mais novo de cada transação. --dry-run nunca migra o banco.
Uso: python -m tools.corrigir_moeda [--dry-run] [--banco CAMINHO] [--bruto PASTA]"""
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

from gabi.db import conectar, migrar, transacao
from gabi.dinheiro.moeda import ValorIlegivel, valor_lancamento


def _estrangeiras(bruto_base: Path) -> tuple[set, dict]:
    """(ids vistos no bruto, {id: transação} em moeda estrangeira), lendo do arquivo mais antigo ao mais novo: vale o mais novo de cada id."""
    vistos, fora = set(), {}
    arquivos = sorted((Path(bruto_base) / "open-finance").glob("*/*/*.jsonl.gz"), key=lambda p: (p.parent.parent.name, p.parent.name, p.name))
    for arq in arquivos:
        with gzip.open(arq, "rt", encoding="utf-8") as f:
            for linha in f:
                x = json.loads(linha)
                t = x.get("dado") if x.get("tipo") == "transacao" else None
                if not isinstance(t, dict) or t.get("id") is None:
                    continue
                vistos.add(t["id"])
                if str(t.get("currencyCode") or "").strip().upper() not in ("", "BRL"):
                    fora[t["id"]] = t
                else:
                    fora.pop(t["id"], None)
    return vistos, fora


def corrigir(con, bruto_base: Path, dry_run: bool = False) -> dict:
    """Só toca lançamentos cuja transação bruta MAIS NOVA é em moeda estrangeira; BRL nunca é alterado."""
    vistos, fora = _estrangeiras(bruto_base)
    mudancas, sem_bruto, diferenca, ilegiveis = [], 0, 0, 0
    linhas = con.execute("select l.id, l.externo_id, l.valor_centavos, l.moeda, l.valor_original_centavos, l.convertido, c.tipo "
                         "from lancamento l join conta c on c.id=l.conta_id").fetchall()
    for l in linhas:
        if l["externo_id"] not in vistos:
            sem_bruto += 1
            continue
        t = fora.get(l["externo_id"])
        if t is None:
            continue
        try:
            v = valor_lancamento(t, l["tipo"])
        except ValorIlegivel:  # mesmo critério da captura: pula e conta, nunca grava valor inventado
            ilegiveis += 1
            continue
        novo = (v.centavos, v.moeda, v.original_centavos, 1 if v.convertido else 0)
        if novo != (l["valor_centavos"], l["moeda"], l["valor_original_centavos"], l["convertido"]):
            mudancas.append((l["id"], novo))
            diferenca += v.centavos - l["valor_centavos"]
    if not dry_run and mudancas:
        with transacao(con):
            for lid, n in mudancas:
                con.execute("update lancamento set valor_centavos=?, moeda=?, valor_original_centavos=?, convertido=? where id=?", (*n, lid))
    return {"lidos": len(linhas), "mudariam": len(mudancas), "diferenca_centavos": diferenca, "sem_bruto": sem_bruto, "ilegiveis": ilegiveis, "aplicado": not dry_run}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    raiz = Path(os.environ.get("GABI_DADOS", "/var/lib/gabi-brain"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", str(raiz / "gabi.db")))
    ap.add_argument("--bruto", default=str(raiz / "bruto"))
    a = ap.parse_args(argv)
    if a.dry_run and not Path(a.banco).exists():
        print(f"banco não encontrado: {a.banco}")
        return 2
    con = conectar(Path(a.banco))
    if a.dry_run:  # somente leitura: nunca migra
        if "moeda" not in [r[1] for r in con.execute("pragma table_info(lancamento)")]:
            print("migração 0022 não aplicada neste banco: aplique-a (rodando sem --dry-run ou a rotina normal) antes de simular")
            return 2
    else:
        migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    r = corrigir(con, Path(a.bruto), dry_run=a.dry_run)
    print(f"{'DRY-RUN: ' if a.dry_run else ''}lidos={r['lidos']} mudariam={r['mudariam']} diferenca_centavos={r['diferenca_centavos']} sem_bruto={r['sem_bruto']} ilegiveis={r['ilegiveis']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
