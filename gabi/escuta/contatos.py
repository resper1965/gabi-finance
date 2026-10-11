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
from gabi.fontes.google_contatos import ErroGoogleContatos

CONTAS_PADRAO = ["resper@gmail.com", "resper@ness.com.br"]
DESTINO_PADRAO, ORIGEM_PADRAO = "resper@gmail.com", "resper@ness.com.br"
_E164 = re.compile(r"^\+\d{10,15}$")
_CANONICO = re.compile(r"^\+[1-9]\d{7,14}$")
_RAMAL = re.compile(r"(?i)(ramal|\bext|\br\.|\bx\s*\d|#|;|,)")


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


def _telefone(item) -> str | None:
    """E.164 de um contato. Prefere o `canonico` (canonicalForm do Google); sem ele, recusa o que normalizar_telefone (que só entende
    Brasil e antepõe 55) transformaria em número brasileiro errado: DDI diferente de 55 e ramal."""
    if not isinstance(item, dict):
        return None
    canon = item.get("canonico")
    if isinstance(canon, str) and _CANONICO.match(canon.strip()):
        return canon.strip()
    bruto = item.get("telefone")
    if not isinstance(bruto, str):
        return None
    t = bruto.strip()
    if _RAMAL.search(t):
        return None
    if t.startswith("00"):
        t = "+" + t[2:]
    if t.startswith("+") and not re.sub(r"\D", "", t).startswith("55"):
        return None
    return normalizar_telefone(t)


def _erro(e: Exception) -> str:
    return str(e) if isinstance(e, ErroGoogleContatos) else type(e).__name__


def sincronizar(con, contas: list[str], listar: Callable[[str], list[dict]]) -> dict:
    """Resultado por conta: cada `listar` roda no seu try; sucesso substitui SÓ as linhas daquela conta (a falha na paginação levanta antes de
    devolver, então nunca se grava lista parcial); falha deixa as linhas dela como estão. Só contas fora do parâmetro são apagadas.
    Devolve só contagens e o erro tipado por conta: {"contas": {conta: {"lidos": n} | {"erro": msg}}, "total", "invalidos"}."""
    contas = list(dict.fromkeys(contas))
    resultado, lidas, invalidos = {}, {}, 0
    for conta in contas:
        try:
            itens = listar(conta)
            falha = None
        except Exception as e:  # noqa: BLE001 - uma conta ruim não derruba as outras
            itens, falha = None, _erro(e)
        if falha is not None:
            resultado[conta] = {"erro": falha}
            continue
        linhas: dict[str, str | None] = {}
        for it in itens:
            tel = _telefone(it)
            if tel is None:
                invalidos += 1
                continue
            nome = it.get("nome")
            nome = nome.strip()[:200] if isinstance(nome, str) and nome.strip() else None
            if tel not in linhas or (linhas[tel] is None and nome):
                linhas[tel] = nome
        lidas[conta] = linhas
        resultado[conta] = {"lidos": len(itens)}
    with transacao(con):
        marcas = ",".join("?" * len(contas))
        con.execute(f"delete from contato_google where conta not in ({marcas})" if contas else "delete from contato_google", contas)
        for conta, linhas in lidas.items():
            con.execute("delete from contato_google where conta=?", (conta,))
            con.executemany("insert into contato_google(conta, telefone, nome) values (?,?,?)", [(conta, t, n) for t, n in linhas.items()])
    total = con.execute("select count(distinct telefone) from contato_google").fetchone()[0]
    return {"contas": resultado, "total": total, "invalidos": invalidos}


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
    """Só contagens e as contas que falharam (pelo nome). Sai com erro quando TODAS falham ou quando alguma falha não é "não autorizada"
    (conta ainda sem refresh token é esperado e não deve acionar o aviso de falha todo dia)."""
    banco = Path(banco or os.environ.get("GABI_BANCO", "/var/lib/gabi-brain/gabi.db"))
    sock = os.environ.get("GABI_FONTES_SOCKET")
    if listar is None:
        if not sock:
            print("ERRO: GABI_FONTES_SOCKET não configurado", file=sys.stderr)
            return 2
        from gabi.fontes.ponte import PonteContatos
        ponte = PonteContatos(sock)
        if not ponte.configurada():
            print("ERRO: contatos do Google não configurados no serviço de fontes", file=sys.stderr)
            return 2
        listar = ponte.listar
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        contas = contas_contatos(con)
        r = sincronizar(con, contas, listar)
    finally:
        con.close()
    ok = {k: v for k, v in r["contas"].items() if "lidos" in v}
    erros = {k: v["erro"] for k, v in r["contas"].items() if "erro" in v}
    print(f"contatos: total={r['total']} invalidos={r['invalidos']} contas_ok={len(ok)} lidos={sum(v['lidos'] for v in ok.values())}")
    for conta, msg in erros.items():
        print(f"AVISO: conta {conta} falhou: {msg}", file=sys.stderr)
    todas = bool(contas) and not ok
    inesperado = any(not m.startswith("conta não autorizada") for m in erros.values())
    return 1 if todas or inesperado else 0


if __name__ == "__main__":
    sys.exit(main())
