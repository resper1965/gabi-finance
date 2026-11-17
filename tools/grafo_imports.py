"""Grafo de imports do pacote `gabi` (so `ast`, nada e importado).

Uso: python -m tools.grafo_imports --fica gabi.dinheiro gabi.cobrar ... [--sai gabi.correio ...]
Imprime (a) o fecho de imports do que fica, (b) os modulos fora do fecho,
(c) as costuras: modulo que fica e importa algo que sai, com arquivo:linha.
`--sai` declara prefixos que saem por decisao: arestas para eles viram costuras e
nao entram no fecho."""
import argparse
import ast
from pathlib import Path


def _nome(raiz: Path, arq: Path) -> str:
    partes = list(arq.relative_to(raiz.parent).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


def modulos(raiz: Path) -> dict[str, Path]:
    return {_nome(raiz, a): a for a in sorted(raiz.rglob("*.py"))}


def _alvos(no, pacote: str, e_pacote: bool, todos: set[str]):
    """Modulos de `todos` referenciados por um no de import."""
    if isinstance(no, ast.Import):
        bases = [(a.name, []) for a in no.names]
    else:
        if no.level:
            partes = pacote.split(".")
            if not e_pacote:
                partes = partes[:-1]
            partes = partes[: len(partes) - (no.level - 1)]
            base = ".".join(partes + ([no.module] if no.module else []))
        else:
            base = no.module or ""
        bases = [(base, [a.name for a in no.names])]
    for base, nomes in bases:
        if base in todos:
            yield base
        for n in nomes:
            if f"{base}.{n}" in todos:
                yield f"{base}.{n}"


def _pais(nome: str):
    partes = nome.split(".")
    for i in range(1, len(partes)):
        yield ".".join(partes[:i])


def arestas(raiz: Path) -> dict[str, list[tuple[str, int]]]:
    mods = modulos(raiz)
    todos = set(mods)
    saida: dict[str, list[tuple[str, int]]] = {}
    for nome, arq in mods.items():
        e_pacote = arq.name == "__init__.py"
        arv = ast.parse(arq.read_text(encoding="utf-8"), filename=str(arq))
        lista = []
        for no in ast.walk(arv):
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                for alvo in _alvos(no, nome, e_pacote, todos):
                    lista.append((alvo, no.lineno))
        saida[nome] = lista
    return saida


def _casa(nome: str, prefixos) -> bool:
    return any(nome == p or nome.startswith(p + ".") for p in prefixos)


def analisar(raiz: Path, fica: list[str], sai: list[str] | None = None):
    sai = sai or []
    g = arestas(raiz)
    mods = modulos(raiz)
    comeco = [m for m in g if _casa(m, fica)]
    fecho: set[str] = set()
    pilha = list(comeco)
    costuras = []
    while pilha:
        m = pilha.pop()
        if m in fecho:
            continue
        fecho.add(m)
        for p in _pais(m):
            if p in g and p not in fecho:
                pilha.append(p)
        for alvo, linha in g[m]:
            if _casa(alvo, sai) and not _casa(alvo, fica):
                costuras.append((m, alvo, f"{mods[m]}:{linha}"))
            elif alvo not in fecho:
                pilha.append(alvo)
    fora = sorted(set(g) - fecho)
    return sorted(fecho), fora, sorted(set(costuras))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default="gabi")
    ap.add_argument("--fica", nargs="+", required=True)
    ap.add_argument("--sai", nargs="*", default=[])
    a = ap.parse_args(argv)
    fecho, fora, costuras = analisar(Path(a.raiz), a.fica, a.sai)
    print("## FECHO (fica)")
    print("\n".join(fecho))
    print("## SAEM")
    print("\n".join(fora))
    print("## COSTURAS")
    for m, alvo, onde in costuras:
        print(f"{m} -> {alvo} @ {onde}")


if __name__ == "__main__":
    main()
