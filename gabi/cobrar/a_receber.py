"""A receber no mês e se já entrou: uma só consulta, SEM rede, SÓ leitura (R1/R2). Consome: dinheiro.esperados, db (nota_fiscal, recebimento_nota, receber_manual).

Três fontes, mantidas separadas para não somar duas vezes o mesmo dinheiro (o pagador de uma nota pode ser também uma série do extrato):
- `recorrentes`: pagadores que o extrato mostra como normais (esperados.py). Situação: `recebido` (já caiu este mês, com data e valor),
  `a_receber` (ainda dentro do dia costumeiro) ou `atrasado` (passou do dia mais tardio visto e não caiu).
- `manuais`: o que o Ricardo disse no chat ou no painel que vai receber (receber_manual). Aberto sem vencimento é `a_receber`; vencido, `atrasado`; com crédito proposto no extrato, `credito_provavel`
  (ele confirma); `recebido` só com o crédito confirmado e na data dentro do mês. Cancelado e vencimento depois do mês ficam fora. Valor negativo (desconto ou adiantamento) entra e abate o esperado.
- `notas`: NFS-e do Nibo com vencimento neste mês. `recebido` só quando o Ricardo confirmou o crédito no extrato; `credito_provavel` quando a Gabi achou um crédito de mesmo valor e falta ele confirmar; o "pago" do Nibo, defasado,
  vira `nibo_diz_pago` (a conferir), nunca recebimento."""
import calendar
import datetime as dt

from gabi.dinheiro.esperados import entradas_esperadas


def _soma(itens: list[dict], situacao: str, campo: str) -> int:
    return sum(i[campo] or 0 for i in itens if i["situacao"] == situacao)


def a_receber_do_mes(con, hoje: dt.date) -> dict:
    ult = calendar.monthrange(hoje.year, hoje.month)[1]
    recorrentes = []
    for e in entradas_esperadas(con, hoje):
        sit = "recebido" if e["ocorreu_este_mes"] else "atrasado" if e["atrasada"] else "a_receber"
        extrato = None
        if e["recebido_em"]:
            m = e["valor_centavos"]
            extrato = con.execute("select l.descricao_original d, c.apelido a from lancamento l join conta c on c.id=l.conta_id "
                                  "where substr(l.data,1,10)=? and c.tipo='BANK' and c.estado='sim' and l.valor_centavos between ? and ? limit 1",
                                  (e["recebido_em"], m * 0.7, m * 1.3)).fetchone()
        recorrentes.append({"pagador": e["pagador"], "situacao": sit, "esperado_centavos": e["valor_centavos"],
                            "dia_esperado": hoje.replace(day=min(e["dia_tipico"], ult)).isoformat(), "dias_atraso": e["dias_atraso"],
                            "confianca": e["confianca"], "recebido_em": e["recebido_em"], "recebido_centavos": e["recebido_centavos"],
                            "extrato": {"descricao": extrato["d"], "conta": extrato["a"]} if extrato else None})
    recorrentes.sort(key=lambda i: ({"atrasado": 0, "a_receber": 1, "recebido": 2}[i["situacao"]], -i["esperado_centavos"]))

    confirmadas = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "select rn.nota_id, l.data, l.valor_centavos, l.descricao_original from recebimento_nota rn join lancamento l on l.id=rn.lancamento_id where rn.estado='confirmado'")}
    propostas = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "select rn.nota_id, l.data, l.valor_centavos, l.descricao_original from recebimento_nota rn join lancamento l on l.id=rn.lancamento_id "
        "where rn.estado='proposto' order by rn.confianca")}
    ini, fim = hoje.replace(day=1).isoformat(), hoje.replace(day=ult).isoformat()
    notas = []
    for n in con.execute("select id, numero, tomador_nome, vencimento, valor_liquido_centavos, nibo_pago from nota_fiscal "
                         "where status='autorizada' and vencimento>=? and vencimento<=? order by vencimento, numero", (ini, fim)):
        rec = confirmadas.get(n["id"])
        prop = None if rec else propostas.get(n["id"])
        sit = ("recebido" if rec else "credito_provavel" if prop else "nibo_diz_pago" if n["nibo_pago"] else "atrasado" if n["vencimento"] < hoje.isoformat() else "a_receber")
        achado = rec or prop
        notas.append({"numero": n["numero"], "pagador": n["tomador_nome"], "situacao": sit, "esperado_centavos": n["valor_liquido_centavos"] or 0,
                      "vencimento": n["vencimento"], "recebido_em": achado[0][:10] if achado else None, "recebido_centavos": achado[1] if achado else None,
                      "extrato": {"descricao": achado[2]} if achado else None})

    manuais = []
    prop_manual = {}
    for p in con.execute("select p.id, p.receber_id, p.confianca, p.motivo, l.data, l.descricao_original, l.valor_centavos from receber_manual_proposta p "
                         "join lancamento l on l.id=p.lancamento_id where p.estado='proposto' order by p.confianca, p.id desc"):
        prop_manual[p["receber_id"]] = p     # a de maior confiança (e a mais antiga) por último, vence
    for m in con.execute("select m.*, l.data ldata, l.valor_centavos lvalor, l.descricao_original ldesc, c.apelido lconta from receber_manual m "
                         "left join lancamento l on l.id=m.lancamento_id left join conta c on c.id=l.conta_id where m.estado in ('aberto','recebido')"):
        prop = prop_manual.get(m["id"]) if m["estado"] == "aberto" else None
        if m["estado"] == "recebido":
            if not (m["ldata"] and ini <= m["ldata"][:10] <= fim):
                continue
            sit = "recebido"
        else:
            if m["vencimento"] and m["vencimento"] > fim:
                continue
            sit = "credito_provavel" if prop else "atrasado" if m["vencimento"] and m["vencimento"] < hoje.isoformat() else "a_receber"
        manuais.append({"id": m["id"], "pagador": m["pagador"], "situacao": sit, "esperado_centavos": m["valor_centavos"], "vencimento": m["vencimento"],
                        "conta": m["conta"], "observacao": m["observacao"],
                        "recebido_em": m["ldata"][:10] if sit == "recebido" else prop["data"][:10] if prop else None,
                        "recebido_centavos": m["lvalor"] if sit == "recebido" else prop["valor_centavos"] if prop else None,
                        "extrato": ({"descricao": m["ldesc"], "conta": m["lconta"]} if sit == "recebido" else {"descricao": prop["descricao_original"]} if prop else None),
                        "proposta": {"id": prop["id"], "confianca": prop["confianca"], "motivo": prop["motivo"], "data": prop["data"],
                                     "descricao": prop["descricao_original"], "valor_centavos": prop["valor_centavos"]} if prop else None})
    manuais.sort(key=lambda i: (-abs(i["esperado_centavos"]), i["id"]))

    def totais(itens):
        return {"esperado_centavos": sum(i["esperado_centavos"] for i in itens),
                "recebido_centavos": sum(i["recebido_centavos"] or 0 for i in itens if i["situacao"] == "recebido"),
                "falta_centavos": sum(_soma(itens, x, "esperado_centavos") for x in ("a_receber", "atrasado", "credito_provavel", "nibo_diz_pago")),
                "atrasado_centavos": _soma(itens, "atrasado", "esperado_centavos")}
    return {"mes": hoje.strftime("%Y-%m"), "recorrentes": recorrentes, "notas": notas, "manuais": manuais,
            "totais": {"recorrentes": totais(recorrentes), "notas": totais(notas), "manuais": totais(manuais)}}
