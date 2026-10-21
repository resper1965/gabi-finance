"""Contatos do Google (nome, telefone e e-mail, só leitura) para dar nome aos remetentes e trazer gente para a escuta.
Sem rede: a leitura vem pela ponte do serviço de fontes (`listar` injetável). Só nome, telefone e e-mail são lidos e gravados (o e-mail vai para `contato_google_email`, migração 0070); saídas e logs só
levam contagens, nunca nome, número nem endereço. Contas e contas de origem/destino são DADO em `parametro` (JSON). Programa do timer: python -m gabi.escuta.contatos."""
import csv
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

from gabi.db import conectar, migrar, transacao
from gabi.correio.regras import endereco
from gabi.escuta.caixa import normalizar_telefone
from gabi.fontes.google_contatos import ErroGoogleContatos

CONTAS_PADRAO = ["resper@gmail.com", "resper@ness.com.br"]
DESTINO_PADRAO, ORIGEM_PADRAO = "resper@gmail.com", "resper@ness.com.br"
_E164 = re.compile(r"^\+\d{10,15}$")
_CANONICO = re.compile(r"^\+[1-9]\d{7,14}$")
MAX_EMAILS = 10
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
    Brasil e antepõe 55) transformaria em número brasileiro errado: ramal, e DDI diferente de 55 só vale se vier com `+`/`00` e 8 a 15 dígitos."""
    if not isinstance(item, dict):
        return None
    canon = item.get("canonico")
    if isinstance(canon, str) and _CANONICO.match(canon.strip()):
        c = canon.strip()
        return (normalizar_telefone(c) or c) if c.startswith("+55") else c  # +55: mesma regra do remetente (celular antigo ganha o 9)
    bruto = item.get("telefone")
    if not isinstance(bruto, str):
        return None
    t = bruto.strip()
    if _RAMAL.search(t):
        return None
    if t.startswith("00"):
        t = "+" + t[2:]
    if t.startswith("+") and not re.sub(r"\D", "", t).startswith("55"):
        digitos = re.sub(r"\D", "", t)
        return "+" + digitos if 8 <= len(digitos) <= 15 else None  # estrangeiro: vale como está, nunca vira +55
    return normalizar_telefone(t)


def _enderecos(item) -> list[str]:
    """E-mails do item já normalizados pelo cliente; aqui só se revalida (a ponte é fronteira) com a mesma regra do correio."""
    brutos = item.get("emails") if isinstance(item, dict) else None
    return list(dict.fromkeys(a for e in (brutos if isinstance(brutos, list) else []) if isinstance(e, str) and (a := endereco(e))))[:MAX_EMAILS]


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
        mails: dict[tuple[str, str], str | None] = {}  # (e-mail, telefone ou '') -> nome
        graph: dict[tuple[str, str], tuple] = {}  # (graph_id, telefone original) -> (nome, E.164 ou None, campo)
        for it in itens:
            tel = _telefone(it)
            nome = it.get("nome")
            nome = nome.strip()[:200] if isinstance(nome, str) and nome.strip() else None
            enderecos = _enderecos(it)
            gid, bruto, campo = it.get("graph_id"), it.get("telefone"), it.get("campo")
            if isinstance(gid, str) and gid and isinstance(bruto, str) and bruto.strip():
                graph.setdefault((gid, bruto), (nome, tel, campo if campo in ("mobile", "home", "business") else None))
            if tel is None:
                if it.get("telefone") or it.get("canonico") or not enderecos:  # telefone inválido (ramal, DDI estranho) ou item vazio; contato só com e-mail não é inválido
                    invalidos += 1
            elif tel not in linhas or (linhas[tel] is None and nome):
                linhas[tel] = nome
            for a in enderecos:
                if (a, tel or "") not in mails or (mails[(a, tel or "")] is None and nome):
                    mails[(a, tel or "")] = nome
        lidas[conta] = (linhas, mails, graph)
        resultado[conta] = {"lidos": len(itens)}
    with transacao(con):
        marcas = ",".join("?" * len(contas))
        con.execute(f"delete from contato_google where conta not in ({marcas})" if contas else "delete from contato_google", contas)
        con.execute(f"delete from contato_google_email where conta not in ({marcas})" if contas else "delete from contato_google_email", contas)
        con.execute(f"delete from contato_graph where conta not in ({marcas})" if contas else "delete from contato_graph", contas)
        for conta, (linhas, mails, graph) in lidas.items():
            con.execute("delete from contato_google where conta=?", (conta,))
            con.executemany("insert into contato_google(conta, telefone, nome) values (?,?,?)", [(conta, t, n) for t, n in linhas.items()])
            con.execute("delete from contato_google_email where conta=?", (conta,))
            con.executemany("insert into contato_google_email(conta, email, telefone, nome) values (?,?,?,?)", [(conta, a, t, n) for (a, t), n in mails.items()])
            con.execute("delete from contato_graph where conta=?", (conta,))
            con.executemany("insert or ignore into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo) values (?,?,?,?,?,?)",
                            [(conta, gid, n, orig, t, campo) for (gid, orig), (n, t, campo) in graph.items()])
    total = con.execute("select count(distinct telefone) from contato_google").fetchone()[0]
    return {"contas": resultado, "total": total, "invalidos": invalidos}


def nome_do_numero(con, numero: str) -> str | None:
    """Nome do contato: o da conta de destino (Gmail) vence o das outras (ness)."""
    destino = conta_destino(con)
    r = con.execute("select nome from contato_google where telefone=? and nome is not null and trim(nome)<>'' "
                    "order by conta=? desc, conta limit 1", (numero, destino)).fetchone()
    return r["nome"] if r else None


def emails_do_numero(con, numero: str) -> list[str]:
    """E-mails distintos (minúsculas, em ordem) dos contatos do Google com este telefone, em qualquer conta."""
    return [r[0] for r in con.execute("select distinct email from contato_google_email where telefone=? order by email", (numero,))]


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
        from gabi.fontes.roteador import contatos_pela_ponte
        listar = contatos_pela_ponte(sock)
        if listar is None:
            print("ERRO: contatos (Google e Graph) não configurados no serviço de fontes", file=sys.stderr)
            return 2
    con = conectar(banco)
    migrar(con, Path(__file__).resolve().parent.parent.parent / "migrations")
    try:
        contas = contas_contatos(con)
        r = sincronizar(con, contas, listar)
        from datetime import datetime, timezone
        from gabi.escuta import contatos_propostas
        g = contatos_propostas.gerar(con, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    finally:
        con.close()
    ok = {k: v for k, v in r["contas"].items() if "lidos" in v}
    erros = {k: v["erro"] for k, v in r["contas"].items() if "erro" in v}
    print(f"contatos: total={r['total']} invalidos={r['invalidos']} contas_ok={len(ok)} lidos={sum(v['lidos'] for v in ok.values())}")
    print(f"propostas: criar={g['criar']} corrigir={g['corrigir']} nomes={g['corrigir_nome']} "
          f"apagar_telefone={g['apagar_telefone']} apagar_contato={g['apagar_contato']} "
          f"adicionar_email={g['adicionar_email']} revisar={g['revisar']}")
    for conta, msg in erros.items():
        print(f"AVISO: conta {conta} falhou: {msg}", file=sys.stderr)
    todas = bool(contas) and not ok
    inesperado = any(not m.startswith("conta não autorizada") for m in erros.values())
    return 1 if todas or inesperado else 0


if __name__ == "__main__":
    sys.exit(main())
