"""Contatos do Google (nome e telefone, só leitura) para dar nome aos remetentes e trazer gente para a escuta.
Sem rede: a leitura vem pela ponte do serviço de fontes (`listar` injetável). Só nome e telefone são lidos e gravados; saídas e logs só
levam contagens. Contas e contas de origem/destino são DADO em `parametro` (JSON). Programa do timer: python -m gabi.escuta.contatos."""
import csv
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

from gabi.db import conectar, migrar, transacao
from gabi.escuta.caixa import normalizar_telefone

CONTAS_PADRAO = ["resper@gmail.com", "resper@ness.com.br"]
DESTINO_PADRAO, ORIGEM_PADRAO = "resper@gmail.com", "resper@ness.com.br"
_E164 = re.compile(r"^\+\d{10,15}$")


def _parametro(con, chave: str, padrao):
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    if r is None:
        return padrao
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return padrao


def contas_contatos(con) -> list[str]:
    v = _parametro(con, "escuta.contas_contatos", CONTAS_PADRAO)
    if not isinstance(v, list):
        return list(CONTAS_PADRAO)
    return list(dict.fromkeys(x for x in v if isinstance(x, str) and x.strip()))


def _conta(con, chave: str, padrao: str) -> str:
    v = _parametro(con, chave, padrao)
    return v if isinstance(v, str) and v.strip() else padrao


def conta_destino(con) -> str:
    """A conta cujo nome vence (o Gmail) e onde o CSV "só na ness" será importado."""
    return _conta(con, "escuta.conta_destino_contatos", DESTINO_PADRAO)


def conta_origem(con) -> str:
    return _conta(con, "escuta.conta_origem_contatos", ORIGEM_PADRAO)


def sincronizar(con, contas: list[str], listar: Callable[[str], list[dict]]) -> dict:
    """Lê todas as contas ANTES de gravar (falha em uma não mexe na tabela). Uma linha por (conta, telefone); conta fora da lista é apagada.
    Devolve só contagens: lidos por conta, total de telefones distintos e inválidos."""
    contas = list(dict.fromkeys(contas))
    lidas, invalidos = {}, 0
    for conta in contas:
        itens = listar(conta)
        linhas: dict[str, str | None] = {}
        for it in itens:
            tel = normalizar_telefone(it.get("telefone")) if isinstance(it, dict) else None
            if tel is None:
                invalidos += 1
                continue
            nome = it.get("nome")
            nome = nome.strip()[:200] if isinstance(nome, str) and nome.strip() else None
            if tel not in linhas or (linhas[tel] is None and nome):
                linhas[tel] = nome
        lidas[conta] = (len(itens), linhas)
    with transacao(con):
        marcas = ",".join("?" * len(contas))
        con.execute(f"delete from contato_google where conta not in ({marcas})" if contas else "delete from contato_google", contas)
        for conta, (_, linhas) in lidas.items():
            con.execute("delete from contato_google where conta=?", (conta,))
            con.executemany("insert into contato_google(conta, telefone, nome) values (?,?,?)", [(conta, t, n) for t, n in linhas.items()])
    total = con.execute("select count(distinct telefone) from contato_google").fetchone()[0]
    return {"contas": {k: v[0] for k, v in lidas.items()}, "total": total, "invalidos": invalidos}


def nome_do_numero(con, numero: str) -> str | None:
    """Nome do contato: o da conta de destino (Gmail) vence o das outras (ness)."""
    destino = conta_destino(con)
    r = con.execute("select nome from contato_google where telefone=? and nome is not null and trim(nome)<>'' "
                    "order by conta=? desc, conta limit 1", (numero, destino)).fetchone()
    return r["nome"] if r else None


def listar_unicos(con) -> list[dict]:
    """Um item por telefone: nome (o do Gmail vence), contas em que existe. Ordenado por nome e telefone."""
    destino = conta_destino(con)
    por: dict[str, dict] = {}
    for r in con.execute("select conta, telefone, nome from contato_google order by conta=? desc, conta", (destino,)):
        d = por.setdefault(r["telefone"], {"nome": None, "telefone": r["telefone"], "contas": []})
        if d["nome"] is None and r["nome"] and r["nome"].strip():
            d["nome"] = r["nome"]
        d["contas"].append(r["conta"])
    return sorted(por.values(), key=lambda d: ((d["nome"] or "~").casefold(), d["telefone"]))


def so_na(con, origem: str, destino: str) -> list[dict]:
    """Contatos que estão em `origem` e não estão em `destino` (pelo telefone normalizado)."""
    linhas = con.execute("select telefone, nome from contato_google where conta=? and telefone not in "
                         "(select telefone from contato_google where conta=?)", (origem, destino)).fetchall()
    return sorted(({"nome": r["nome"], "telefone": r["telefone"]} for r in linhas), key=lambda d: ((d["nome"] or "~").casefold(), d["telefone"]))


def _celula(nome) -> str:
    n = nome if isinstance(nome, str) else ""
    return "'" + n if n[:1] in ("=", "+", "-", "@", "\t", "\r") else n


def csv_google(contatos: list[dict]) -> str:
    """CSV do importador do Google (`Name,Phone 1 - Value`), RFC 4180. Só nome e telefone E.164; nome que parece fórmula ganha apóstrofo."""
    saida = io.StringIO()
    w = csv.writer(saida, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(["Name", "Phone 1 - Value"])
    for c in contatos:
        tel = c.get("telefone")
        if isinstance(tel, str) and _E164.match(tel):
            w.writerow([_celula(c.get("nome")), tel])
    return saida.getvalue()


def main(banco: Path | None = None, *, listar=None) -> int:
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sock = os.environ.get("GABI_FONTES_SOCKET")
    if listar is None:
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.google_contatos import ErroGoogleContatos
        from gabi.fontes.ponte import PonteContatos
        ponte = PonteContatos(sock)
        if not ponte.configurada():
            print("ERRO: contatos do Google não configurados no serviço de fontes", file=sys.stderr)
            return 2
        listar = ponte.listar
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        r = sincronizar(con, contas_contatos(con), listar)
    except Exception as e:  # noqa: BLE001 - só o tipo e, se for erro tipado da fonte, a mensagem (só cita a conta)
        from gabi.fontes.google_contatos import ErroGoogleContatos
        print(f"ERRO: {e if isinstance(e, ErroGoogleContatos) else type(e).__name__}", file=sys.stderr)
        return 1
    finally:
        con.close()
    print(f"contatos: total={r['total']} invalidos={r['invalidos']} " + " ".join(f"contas[{i}]={n}" for i, (_, n) in enumerate(r["contas"].items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
