"""Refaz valor_centavos, moeda, valor_original_centavos e convertido dos lançamentos a partir do bruto imutável (sem rede), com a mesma
regra da captura (gabi.dinheiro.moeda). Idempotente. --dry-run só imprime contagens. Nunca imprime descrição nem valor por lançamento.
Uso: python -m tools.corrigir_moeda [--dry-run] [--banco CAMINHO] [--bruto PASTA]"""
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

from gabi.db import conectar, migrar, transacao
from gabi.dinheiro.moeda import valor_lancamento


def _transacoes(bruto_base: Path, ref: str, cache: dict) -> dict:
    """{id: transação crua} do arquivo `ref` (nome gravado em lancamento.bruto_ref); {} se o arquivo não existe."""
    if ref not in cache:
        achados = sorted((Path(bruto_base) / "open-finance").glob(f"*/*/{ref}")) if ref and "/" not in ref else []
        itens = {}
        if achados:
            with gzip.open(achados[0], "rt", encoding="utf-8") as f:
                for linha in f:
                    x = json.loads(linha)
                    if x.get("tipo") == "transacao" and isinstance(x.get("dado"), dict) and x["dado"].get("id") is not None:
                        itens[x["dado"]["id"]] = x["dado"]
        cache[ref] = itens
    return cache[ref]


def corrigir(con, bruto_base: Path, dry_run: bool = False) -> dict:
    cache, mudancas, sem_bruto, diferenca = {}, [], 0, 0
    linhas = con.execute("select l.id, l.externo_id, l.valor_centavos, l.moeda, l.valor_original_centavos, l.convertido, l.bruto_ref, c.tipo "
                         "from lancamento l join conta c on c.id=l.conta_id").fetchall()
    for l in linhas:
        t = _transacoes(bruto_base, l["bruto_ref"], cache).get(l["externo_id"])
        if t is None:
            sem_bruto += 1
            continue
        v = valor_lancamento(t, l["tipo"])
        novo = (v.centavos, v.moeda, v.original_centavos, 1 if v.convertido else 0)
        if novo != (l["valor_centavos"], l["moeda"], l["valor_original_centavos"], l["convertido"]):
            mudancas.append((l["id"], novo))
            diferenca += v.centavos - l["valor_centavos"]
    if not dry_run and mudancas:
        with transacao(con):
            for lid, n in mudancas:
                con.execute("update lancamento set valor_centavos=?, moeda=?, valor_original_centavos=?, convertido=? where id=?", (*n, lid))
    return {"lidos": len(linhas), "mudariam": len(mudancas), "diferenca_centavos": diferenca, "sem_bruto": sem_bruto, "aplicado": not dry_run}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    raiz = Path(os.environ.get("GABI_DADOS", "/var/lib/gabi-brain"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", str(raiz / "gabi.db")))
    ap.add_argument("--bruto", default=str(raiz / "bruto"))
    a = ap.parse_args(argv)
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent / "migrations")
    r = corrigir(con, Path(a.bruto), dry_run=a.dry_run)
    print(f"{'DRY-RUN: ' if a.dry_run else ''}lidos={r['lidos']} mudariam={r['mudariam']} diferenca_centavos={r['diferenca_centavos']} sem_bruto={r['sem_bruto']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
