"""Aplica `seeds/categorias-pessoais.csv`: cria as categorias pessoais (e seu grupo) e as equivalências com as categorias do banco.
Dados em arquivo editável, fora do código (R6). Idempotente; nunca sobrescreve uma equivalência já escolhida pelo Ricardo.
Uso: python -m tools.semear_categorias [--arquivo CAMINHO] [--banco CAMINHO]. Consome: rotas.cadastros (mesma validação e auditoria dos Cadastros)."""
import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from gabi.db import conectar, transacao
from gabi.rotas.cadastros import TIPOS, _auditar

COLUNAS = ("categoria", "grupo", "equivale_nibo", "origens_banco")


@dataclass
class Resumo:
    categorias_criadas: int = 0
    equivalencias_criadas: int = 0
    conflitos: list[str] = field(default_factory=list)            # origem do banco que já aponta para outra categoria (mantida)
    nibo_nao_encontrados: list[str] = field(default_factory=list)  # "categoria -> nome do Nibo" sem correspondente


def _ler(arquivo: Path) -> list[dict]:
    with open(arquivo, encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f, delimiter=";")
        if tuple(leitor.fieldnames or ()) != COLUNAS:
            raise ValueError(f"colunas esperadas: {';'.join(COLUNAS)}")
        linhas = [{k: (v or "").strip() for k, v in l.items()} for l in leitor]
    for l in linhas:
        if not l["categoria"] or not l["grupo"]:
            raise ValueError(f"linha sem categoria ou grupo: {l}")
    return linhas


def aplicar(con, arquivo: Path, quem: str) -> Resumo:
    linhas = _ler(Path(arquivo))  # valida tudo antes de gravar qualquer coisa
    r, C = Resumo(), TIPOS["categorias"]
    ids = {x["nome"]: x["id"] for x in con.execute("select id, nome from categoria where excluido_em is null")}
    nibo = {x["nome"]: x["nibo_category_id"] for x in con.execute("select nome, nibo_category_id from categoria where nibo_category_id is not null and excluido_em is null")}
    for l in linhas:
        if l["grupo"] not in ids:
            ids[l["grupo"]] = C.criar(con, {"nome": l["grupo"]}, quem, "categorias")["id"]
            r.categorias_criadas += 1
        if l["categoria"] not in ids:
            corpo = {"nome": l["categoria"], "pai_id": ids[l["grupo"]]}
            if l["equivale_nibo"]:
                if l["equivale_nibo"] in nibo:
                    corpo["nibo_category_id"] = nibo[l["equivale_nibo"]]
                else:
                    r.nibo_nao_encontrados.append(f"{l['categoria']} -> {l['equivale_nibo']}")
            ids[l["categoria"]] = C.criar(con, corpo, quem, "categorias")["id"]
            r.categorias_criadas += 1
        for origem in filter(None, (o.strip() for o in l["origens_banco"].split("|"))):
            atual = con.execute("select categoria_id from equivalencia_categoria where origem_pluggy=?", (origem,)).fetchone()
            if atual is None:
                with transacao(con):
                    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values (?,?)", (origem, ids[l["categoria"]]))
                    _auditar(con, quem, "categorias/equivalencias", origem, "alterada")
                r.equivalencias_criadas += 1
            elif atual["categoria_id"] != ids[l["categoria"]]:
                r.conflitos.append(origem)
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", default=str(Path(__file__).resolve().parent.parent / "seeds" / "categorias-pessoais.csv"))
    ap.add_argument("--banco", default="/var/lib/gabi-finance/gabi.db")
    a = ap.parse_args()
    resumo = aplicar(conectar(a.banco), Path(a.arquivo), "claude (a pedido do Ricardo: categorias pessoais)")
    print(f"categorias criadas={resumo.categorias_criadas} equivalencias criadas={resumo.equivalencias_criadas} conflitos={resumo.conflitos} nibo_nao_encontrados={resumo.nibo_nao_encontrados}")
    sys.exit(0)
