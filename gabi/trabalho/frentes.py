"""Frentes de trabalho (cliente, prospect, projeto...). A Gabi SUGERE que um item entra numa frente; só entra com a confirmação (R1).
A regra de cada frente (dominios, pessoas, palavras) é cadastro do Ricardo, nunca código (R6)."""
import datetime as dt
import json
from dataclasses import dataclass

from gabi.db import transacao

TIPOS = ("cliente", "prospect", "projeto", "interno", "pessoal")


@dataclass(frozen=True)
class Candidata:
    frente_id: int
    motivo: str


def abrir_frente(con, nome: str, tipo: str, empresa_id: str | None, regra: dict | None) -> int:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de frente inválido: {tipo!r}")
    cur = con.execute("insert into frente(nome, tipo, empresa_id, regra) values (?,?,?,?)",
                      (nome, tipo, empresa_id, json.dumps(regra) if regra else None))
    return cur.lastrowid


def reconhecer(con, item) -> list[Candidata]:
    dominio = (item["remetente"] or "").lower().rpartition("@")[2]
    texto = f"{item['assunto'] or ''} {item['trecho'] or ''}".lower()
    achadas = []
    for f in con.execute("select id, regra from frente where regra is not null"):
        regra = json.loads(f["regra"])
        for d in regra.get("dominios", []):
            if dominio == d.lower() or dominio.endswith("." + d.lower()):
                achadas.append(Candidata(f["id"], f"domínio {d}"))
                break
        else:
            for p in regra.get("palavras", []):
                if p.lower() in texto:
                    achadas.append(Candidata(f["id"], f"palavra {p}"))
                    break
    return achadas


def sugerir(con, item) -> list[Candidata]:
    """Grava como 'sugerido'; não aparece dentro da frente até a confirmação."""
    cands = reconhecer(con, item)
    for c in cands:
        con.execute("insert or ignore into item_frente(frente_id, tipo, ref_id, origem, estado) values (?, 'email', ?, ?, 'sugerido')",
                    (c.frente_id, item["id"], c.motivo))
    return cands


def confirmar(con, frente_id: int, item_id: int, por: str) -> None:
    with transacao(con):
        con.execute("insert into item_frente(frente_id, tipo, ref_id, origem, estado) values (?, 'email', ?, 'manual', 'confirmado') "
                    "on conflict(frente_id, tipo, ref_id) do update set estado='confirmado'", (frente_id, item_id))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'api')",
                    (dt.datetime.now(dt.timezone.utc).isoformat(), por, f"confirmou item {item_id} na frente {frente_id}"))


def itens(con, frente_id: int) -> list[int]:
    return [r[0] for r in con.execute("select ref_id from item_frente where frente_id=? and estado='confirmado' order by ref_id", (frente_id,))]
