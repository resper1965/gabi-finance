"""Casamento de recebimentos: crédito em conta BANK liberada no caixa único com o valor LÍQUIDO de uma NFS-e autorizada. Consome: db (nota_fiscal, lancamento, conta, recebimento_nota).

Não depende do flag `pj`: o C6 PJ entra no caixa único e na conciliação como as demais contas (`bancos_pj` vazio, decisão do Ricardo em 06/10/2026).

Só propõe (estado `proposto`, com confiança e motivo); confirmar ou rejeitar é do Ricardo (R1). Janela: do dia da emissão até 90 dias depois do
vencimento. Confiança: 0,5 pelo valor igual; +0,3 se o crédito cai a até 5 dias do vencimento; +0,2 se o nome ou o CNPJ do tomador está no descritivo."""
import datetime as dt
import re
import unicodedata

from gabi.db import transacao
from gabi.cobrar.util import agora as _agora

JANELA_DIAS, TOLERANCIA_DATA = 90, 5


def _norm(t: str | None) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").upper().split())


def _confianca(nota, l) -> tuple[float, str]:
    conf, partes = 0.5, ["valor igual ao líquido da nota"]
    if nota["vencimento"] and abs((dt.date.fromisoformat(l["data"][:10]) - dt.date.fromisoformat(nota["vencimento"])).days) <= TOLERANCIA_DATA:
        conf += 0.3
        partes.append(f"crédito a até {TOLERANCIA_DATA} dias do vencimento")
    desc = _norm(l["descricao_original"])
    toks = [t for t in _norm(nota["tomador_nome"]).split() if len(t) >= 3][:2]
    doc = re.sub(r"\D", "", nota["tomador_doc"] or "")
    if (toks and all(t in desc for t in toks)) or (len(doc) >= 11 and doc in re.sub(r"\D", "", l["descricao_original"] or "")):
        conf += 0.2
        partes.append("tomador no descritivo")
    return round(min(conf, 1.0), 2), ", ".join(partes)


def propor_recebimentos(con) -> int:
    novas = 0
    notas = con.execute("select * from nota_fiscal n where n.status='autorizada' and n.valor_liquido_centavos is not null and n.valor_liquido_centavos>0 "
                        "and not exists (select 1 from recebimento_nota r where r.nota_id=n.id and r.estado='confirmado')").fetchall()
    with transacao(con):
        for n in notas:
            venc = dt.date.fromisoformat(n["vencimento"]) if n["vencimento"] else None
            ini = (n["emissao"] or (venc - dt.timedelta(days=JANELA_DIAS)).isoformat())[:10] if (n["emissao"] or venc) else "0000-01-01"
            fim = (venc + dt.timedelta(days=JANELA_DIAS)).isoformat() if venc else "9999-12-31"
            for l in con.execute(
                    "select l.* from lancamento l join conta c on c.id=l.conta_id where c.tipo='BANK' and c.estado='sim' and c.excluido_em is null and l.valor_centavos=? and l.data>=? and l.data<=? "
                    "and not exists (select 1 from recebimento_nota r where r.lancamento_id=l.id and r.estado='confirmado')", (n["valor_liquido_centavos"], ini, fim)):
                conf, motivo = _confianca(n, l)
                novas += con.execute("insert or ignore into recebimento_nota(nota_id, lancamento_id, confianca, motivo, criado_em) values (?,?,?,?,?)",
                                     (n["id"], l["id"], conf, motivo, _agora())).rowcount
    return novas


def _proposta(con, rid: int):
    r = con.execute("select * from recebimento_nota where id=?", (rid,)).fetchone()
    if r is None:
        raise LookupError(f"recebimento {rid} não existe")
    if r["estado"] != "proposto":
        raise ValueError(f"recebimento {rid} já foi {r['estado']}")
    return r


def confirmar_recebimento(con, rid: int, por: str) -> None:
    with transacao(con):
        r = _proposta(con, rid)
        con.execute("update recebimento_nota set estado='confirmado' where id=?", (rid,))
        con.execute("update recebimento_nota set estado='rejeitado' where estado='proposto' and id<>? and (nota_id=? or lancamento_id=?)", (rid, r["nota_id"], r["lancamento_id"]))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')", (_agora(), por, f"recebimento {rid} confirmado (nota {r['nota_id']}, lançamento {r['lancamento_id']})"))


def rejeitar_recebimento(con, rid: int, por: str) -> None:
    with transacao(con):
        _proposta(con, rid)
        con.execute("update recebimento_nota set estado='rejeitado' where id=?", (rid,))
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,?,?, 'cobrar')", (_agora(), por, f"recebimento {rid} rejeitado"))
