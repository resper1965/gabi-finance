"""E-mail e agenda da Fase 3. Guarda SÓ cabeçalho e trecho (o corpo fica na origem); nada é apagado nem enviado daqui (R1, R2).
Consome: caixa_email (estado 'sim' libera a leitura), parametro 'email_palavras_relevantes', pessoa.dados.emails."""
import datetime as dt
import json
from dataclasses import dataclass
from typing import Callable

from gabi.db import transacao

TAM_TRECHO = 280
SLOT_MIN = 30
Fonte = Callable[[dict, str | None], tuple[list[dict], str | None]]


@dataclass(frozen=True)
class ResumoRodada:
    novos: int
    duplicados: int


@dataclass(frozen=True)
class Conflito:
    evento_a: int
    evento_b: int
    sugestao_inicio: str  # proposta: só sai após confirmação do Ricardo


def _json(con, chave: str) -> list[str]:
    r = con.execute("select valor from parametro where chave=?", (chave,)).fetchone()
    return [p.lower() for p in json.loads(r[0])] if r else []


def marcar_relevante(con, remetente: str, assunto: str | None) -> tuple[bool, str]:
    """Regra: remetente conhecido, depois palavra cadastrada. Sempre devolve o motivo (também quando não é relevante)."""
    rem = (remetente or "").lower()
    for p in con.execute("select nome, dados from pessoa where excluido_em is null" if _tem_excluido(con) else "select nome, dados from pessoa"):
        emails = [e.lower() for e in (json.loads(p["dados"] or "{}").get("emails") or [])]
        if rem in emails:
            return True, f"remetente conhecido: {p['nome']}"
    texto = (assunto or "").lower()
    for palavra in _json(con, "email_palavras_relevantes"):
        if palavra in texto:
            return True, f"palavra cadastrada: {palavra}"
    return False, "nenhuma regra casou"


def _tem_excluido(con) -> bool:
    return any(c[1] == "excluido_em" for c in con.execute("pragma table_info(pessoa)"))


def ingerir_email(con, caixa_id: int, fonte: Fonte) -> ResumoRodada:
    caixa = con.execute("select * from caixa_email where id=?", (caixa_id,)).fetchone()
    if caixa is None or caixa["estado"] != "sim" or not caixa["le"]:
        return ResumoRodada(0, 0)
    msgs, novo_cursor = fonte(dict(caixa), caixa["cursor"])
    novos = dup = 0
    with transacao(con):
        for m in msgs:
            if caixa["ler_a_partir_de"] and m["recebido_em"] < caixa["ler_a_partir_de"]:
                continue
            if con.execute("select 1 from item_email where message_id=?", (m["message_id"],)).fetchone():
                dup += 1  # Google e Graph entregam o mesmo Message-ID na migração da ness
                continue
            rel, motivo = marcar_relevante(con, m["remetente"], m.get("assunto"))
            con.execute("insert into item_email(caixa_id, message_id, remetente, assunto, recebido_em, trecho, frente_id, relevante, motivo) "
                        "values (?,?,?,?,?,?,?,?,?)",
                        (caixa_id, m["message_id"], m["remetente"], m.get("assunto"), m["recebido_em"],
                         (m.get("corpo") or m.get("trecho") or "")[:TAM_TRECHO], caixa["frente_padrao_id"], int(rel), motivo))
            novos += 1
        con.execute("update caixa_email set cursor=? where id=?", (novo_cursor, caixa_id))  # cursor só avança junto com a gravação
    return ResumoRodada(novos, dup)


def expurgo_sugerido(con) -> list[int]:
    """SÓ sugere (ids). Sem regra ligada pelo Ricardo, devolve vazio; quem apaga é uma ação explícita do painel."""
    ids: set[int] = set()
    for r in con.execute("select remetente_contem, assunto_contem from regra_expurgo where ligada=1"):
        cond, args = ["estado='novo'"], []
        if r["remetente_contem"]:
            cond.append("lower(remetente) like ?"); args.append(f"%{r['remetente_contem'].lower()}%")
        if r["assunto_contem"]:
            cond.append("lower(assunto) like ?"); args.append(f"%{r['assunto_contem'].lower()}%")
        if len(cond) == 1:
            continue  # regra vazia casaria tudo
        ids.update(x[0] for x in con.execute(f"select id from item_email where {' and '.join(cond)}", args))
    return sorted(ids)


def conflitos(con, de: str, ate: str) -> list[Conflito]:
    ev = con.execute("select id, inicio, fim from evento where inicio < ? and fim > ? order by inicio", (ate, de)).fetchall()
    achados = []
    for i, a in enumerate(ev):
        for b in ev[i + 1:]:
            if b["inicio"] < a["fim"]:
                livre = max(a["fim"], b["fim"])
                achados.append(Conflito(a["id"], b["id"], livre))
    return achados
