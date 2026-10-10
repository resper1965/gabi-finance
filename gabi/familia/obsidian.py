"""Exportação para o cofre Obsidian (T4.6, leitura): .md de família (com CPF), saúde, frentes, decisões e memória, UMA PASTA POR PESSOA.
O que cada pessoa recebe vem da matriz de acesso (`grau` do nível dela): `total` = tudo; `parcial` = só o que é dela (família e saúde); `nenhum` = nada.
Determinística (sem data/hora nos arquivos). Edição feita fora (arquivo diferente do exportado) vira `edicao_externa` pendente para o Ricardo decidir; o arquivo
editado NÃO é sobrescrito enquanto a edição estiver pendente e o banco nunca muda sozinho (R1). Sincronizar só por Tailscale/Syncthing ou nuvem criptografada.
Consome: pessoa, acesso, matriz_acesso, frente, decisao, memoria, edicao_externa, familia.saude."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from gabi.familia.saude import Cofre, marcadores, serie
from gabi.identidade import NIVEIS, grau

MANIFESTO = ".gabi-manifest.json"
MAX_DECISOES = 500


def _nome_arquivo(nome: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", nome).strip() or "sem-nome"


def _nivel_de(con, pessoa_id: str) -> str:
    niveis = [r[0] for r in con.execute("select nivel from acesso where pessoa_id=?", (pessoa_id,))]
    return max(niveis, key=NIVEIS.index) if niveis else "terceiros"


def _familia(con, pessoa) -> str:
    dados = json.loads(pessoa["dados"] or "{}")
    linhas = [f"# {pessoa['nome']}", "", f"- Papel: {pessoa['papel'] or '—'}", f"- Telefone: {pessoa['telefone'] or '—'}"]
    for d in dados.get("documentos") or []:
        linhas.append(f"- {d.get('tipo', 'Documento')}: {d.get('numero', '—')}")
    return "\n".join(linhas) + "\n"


def _saude(s: Cofre, pessoa, quem: str) -> str:
    linhas = [f"# Saúde · {pessoa['nome']}", ""]
    ms = marcadores(s, pessoa["id"], quem)
    if not ms:
        linhas.append("Sem exames registrados.")
    for m in ms:
        linhas += [f"## {m['marcador']}", f"Último: {m['valor']} {m['unidade'] or ''} em {m['em']}{' (fora da faixa)' if m['fora_da_faixa'] else ''}".replace("  ", " "), ""]
        linhas += [f"- {p.em.isoformat()}: {p.valor} {p.unidade or ''}{' (fora da faixa)' if p.fora_da_faixa else ''}".replace("  ", " ") for p in serie(s, pessoa["id"], m["marcador"], quem)]
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


def _frentes(con) -> str:
    linhas = ["# Frentes", ""]
    for f in con.execute("select f.nome, f.tipo, e.nome empresa from frente f left join empresa e on e.id=f.empresa_id order by f.nome, f.id"):
        linhas.append(f"- {f['nome']} ({f['tipo']}{', ' + f['empresa'] if f['empresa'] else ''})")
    return "\n".join(linhas) + "\n"


def _decisoes(con) -> str:
    linhas = ["# Decisões", ""]
    linhas += [f"- {r['quando'][:10]} · {r['quem']}: {r['o_que']}" for r in con.execute("select * from (select * from decisao order by id desc limit ?) order by id", (MAX_DECISOES,))]
    return "\n".join(linhas) + "\n"


def _memoria(con) -> dict[str, str]:
    por_tipo: dict[str, list[str]] = {}
    for r in con.execute("select chave, tipo, texto from memoria order by tipo, id"):
        por_tipo.setdefault(r["tipo"], []).append(f"## {r['chave']}\n{r['texto']}\n")
    return {f"Memoria/{_nome_arquivo(t)}.md": f"# Memória · {t}\n\n" + "\n".join(v) for t, v in sorted(por_tipo.items())}


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def importar_edicoes(con, pasta: Path, pessoa_id: str) -> int:
    """Arquivos da pasta diferentes do que foi exportado viram `edicao_externa` pendente (uma por conteúdo). Devolve quantas são novas."""
    manifesto_arq = pasta / MANIFESTO
    if not manifesto_arq.exists():
        return 0
    n = 0
    agora = dt.datetime.now(dt.timezone.utc).isoformat()
    for rel, h in json.loads(manifesto_arq.read_text(encoding="utf-8")).items():
        arq = pasta / rel
        if not arq.exists():
            continue
        texto = arq.read_text(encoding="utf-8")
        if _hash(texto) != h:
            n += con.execute("insert or ignore into edicao_externa(pessoa_id, arquivo, texto, hash, criado_em) values (?,?,?,?,?)",
                             (pessoa_id, rel, texto, _hash(texto), agora)).rowcount
    return n


def exportar_cofre(con, saude: Cofre | None, destino: Path, para: str) -> list[Path]:
    pessoa_alvo = con.execute("select * from pessoa where id=?", (para,)).fetchone()
    if pessoa_alvo is None:
        raise LookupError(f"pessoa {para} não existe")
    nivel = _nivel_de(con, para)
    pasta = Path(destino) / para
    pasta.mkdir(parents=True, exist_ok=True)
    importar_edicoes(con, pasta, para)
    pendentes = {r[0] for r in con.execute("select arquivo from edicao_externa where pessoa_id=? and estado='pendente'", (para,))}

    def pessoas(info: str):
        g = grau(con, info, nivel)
        if g == "total":
            return list(con.execute("select * from pessoa order by nome, id"))
        return [pessoa_alvo] if g == "parcial" else []

    arquivos: dict[str, str] = {}
    for p in pessoas("família"):
        arquivos[f"Familia/{_nome_arquivo(p['nome'])}.md"] = _familia(con, p)
    if saude is not None:
        for p in pessoas("saúde"):
            arquivos[f"Saude/{_nome_arquivo(p['nome'])}.md"] = _saude(saude, p, f"obsidian:{para}")
    if grau(con, "frentes", nivel) == "total":
        arquivos["Frentes.md"] = _frentes(con)
    if grau(con, "decisões", nivel) == "total":
        arquivos["Decisoes.md"] = _decisoes(con)
    if grau(con, "memória", nivel) == "total":
        arquivos.update(_memoria(con))

    antigo = json.loads((pasta / MANIFESTO).read_text(encoding="utf-8")) if (pasta / MANIFESTO).exists() else {}
    manifesto, escritos = {}, []
    for rel in sorted(arquivos):
        arq = pasta / rel
        if rel in pendentes and arq.exists():  # edição pendente: preserva o arquivo e a referência exportada
            manifesto[rel] = antigo.get(rel, _hash(arquivos[rel]))
            continue
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(arquivos[rel], encoding="utf-8")
        manifesto[rel] = _hash(arquivos[rel])
        escritos.append(arq)
    (pasta / MANIFESTO).write_text(json.dumps(manifesto, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return escritos


if __name__ == "__main__":
    import argparse
    import os
    import sys

    from gabi.db import conectar, migrar
    from gabi.familia.ambiente import saude_do_ambiente
    from gabi.familia.saude import abrir_saude

    ap = argparse.ArgumentParser(description="Exporta o cofre Obsidian de UMA pessoa (leitura).")
    ap.add_argument("--banco", default=os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    ap.add_argument("--destino", required=True)
    ap.add_argument("--para", required=True, help="id da pessoa (ex.: p1)")
    a = ap.parse_args()
    con = conectar(Path(a.banco))
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    cfg = saude_do_ambiente(Path(a.banco).parent)
    if cfg:
        with abrir_saude(*cfg) as s:
            n = len(exportar_cofre(con, s, Path(a.destino), a.para))
    else:
        n = len(exportar_cofre(con, None, Path(a.destino), a.para))
    print(f"{n} arquivo(s) escritos em {Path(a.destino) / a.para}")
    sys.exit(0)
