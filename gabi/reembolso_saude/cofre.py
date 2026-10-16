"""Reembolso de saúde DENTRO do cofre cifrado (ADR-014): paciente, prestador, valor, CPF/CNPJ, conselho e especialidade nunca saem daqui para o `gabi.db`.
As tabelas `reembolso_doc` e `reembolso_dossie` são criadas por este módulo no mesmo arquivo do cofre (sem mexer em `gabi/familia/saude.py`).
`id` do dossiê é dado pelo cofre e é o número que o resto do sistema usa. Sem log de leitura aqui: quem lê para o painel registra em `leitura`."""
import datetime as dt
import json

from gabi.familia.saude import Cofre
from gabi.reembolso_saude import dossies

_ESQUEMA = (
    """create table if not exists reembolso_dossie(
         id integer primary key, chave text not null unique, paciente text, prestador text, mes text not null, avisos text not null default '[]')""",
    """create table if not exists reembolso_doc(
         paperless_id integer primary key, dossie_id integer not null, estado text not null, documento text, caso text,
         paciente text, prestador text, valor text, doc_prestador text, conselho text, especialidade text,
         data text not null, adicionado text not null, pedido_em text, protocolo text, confianca real, credito_tx integer)""",
)
_CAMPOS = ("paciente", "prestador", "valor", "doc_prestador", "conselho", "especialidade")


def garantir(s: Cofre) -> None:
    for ddl in _ESQUEMA:
        s.con.execute(ddl)


def _d(v) -> dt.date | None:
    return dt.date.fromisoformat(v) if v else None


def gravar_doc(s: Cofre, doc: dict) -> int:
    """Grava (ou atualiza) o documento e devolve o número do dossiê (par normalizado + mês do atendimento). Uma chamada por documento."""
    garantir(s)
    k = doc.get("chave") or dossies.chave(doc)
    c = doc["campos"]
    achado = s.con.execute("select id from reembolso_dossie where chave=?", (k,)).fetchone()
    if achado:
        did = achado["id"]
        s.con.execute("update reembolso_dossie set paciente=coalesce(?, paciente), prestador=coalesce(?, prestador) where id=?",
                      (c.get("paciente"), c.get("prestador"), did))
    else:
        did = s.con.execute("insert into reembolso_dossie(chave, paciente, prestador, mes) values (?,?,?,?)",
                            (k, c.get("paciente"), c.get("prestador"), f"{doc['data']:%Y-%m}")).lastrowid
    s.con.execute(
        "insert into reembolso_doc(paperless_id, dossie_id, estado, documento, caso, paciente, prestador, valor, doc_prestador, conselho, especialidade, data, "
        "adicionado, pedido_em, protocolo, confianca, credito_tx) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "on conflict(paperless_id) do update set dossie_id=excluded.dossie_id, estado=excluded.estado, documento=excluded.documento, caso=excluded.caso, "
        "paciente=excluded.paciente, prestador=excluded.prestador, valor=excluded.valor, doc_prestador=excluded.doc_prestador, conselho=excluded.conselho, "
        "especialidade=excluded.especialidade, data=excluded.data, adicionado=excluded.adicionado, pedido_em=excluded.pedido_em, protocolo=excluded.protocolo, "
        "confianca=excluded.confianca, credito_tx=excluded.credito_tx",
        (doc["id"], did, doc["estado"], doc.get("documento"), doc.get("caso"), *(c.get(k2) for k2 in _CAMPOS), doc["data"].isoformat(),
         doc["adicionado"].isoformat(), doc["pedido_em"].isoformat() if doc.get("pedido_em") else None, doc.get("protocolo"), doc.get("confianca"),
         doc.get("credito_tx")))
    return did


def _doc(r) -> dict:
    return {"id": r["paperless_id"], "dossie_id": r["dossie_id"], "estado": r["estado"], "documento": r["documento"], "caso": r["caso"],
            "campos": {k: r[k] for k in _CAMPOS if r[k] is not None}, "data": _d(r["data"]), "adicionado": _d(r["adicionado"]),
            "pedido_em": _d(r["pedido_em"]), "protocolo": r["protocolo"], "confianca": r["confianca"], "credito_tx": r["credito_tx"]}


def docs(s: Cofre) -> list[dict]:
    garantir(s)
    return [_doc(r) for r in s.con.execute("select * from reembolso_doc order by paperless_id")]


def dossie(s: Cofre, did: int) -> dict | None:
    garantir(s)
    r = s.con.execute("select * from reembolso_dossie where id=?", (did,)).fetchone()
    return dict(r) if r else None


def dossies_todos(s: Cofre) -> list[dict]:
    garantir(s)
    return [dict(r) for r in s.con.execute("select * from reembolso_dossie order by id")]


def avisos_do_dossie(s: Cofre, did: int) -> list[str]:
    r = dossie(s, did)
    return json.loads(r["avisos"]) if r else []


def gravar_avisos(s: Cofre, did: int, avisos: list[str]) -> None:
    s.con.execute("update reembolso_dossie set avisos=? where id=?", (json.dumps(avisos), did))
