"""Despesas de empresa pagas no PF, por mês: o que o Ricardo pode cobrar da ness/IONIC ou lançar na PJ (ele mesmo; nada é enviado, R2).
Substitui o reembolso PJ, a cobrança e o lote do Nibo (ADR-023). Consome: lancamento, conta, empresa."""
import datetime as dt


def despesas_por_empresa(con, mes: str) -> list[dict]:
    """`mes` = "AAAA-MM". Saídas com empresa marcada, em conta que não é PJ (nem excluída), agrupadas por empresa, do maior total para o menor."""
    try:
        if not isinstance(mes, str) or len(mes) != 7:
            raise ValueError
        ini = dt.date.fromisoformat(mes + "-01")
    except ValueError:
        raise ValueError("mes deve ser AAAA-MM") from None
    fim = (ini.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    grupos: dict[str, dict] = {}
    for r in con.execute(
            "select l.id, l.data, l.descricao_original, -l.valor_centavos as valor, l.empresa_id, coalesce(e.nome, l.empresa_id) as nome "
            "from lancamento l join conta c on c.id=l.conta_id left join empresa e on e.id=l.empresa_id "
            "where l.empresa_id is not null and l.valor_centavos<0 and c.pj=0 and c.excluido_em is null and l.data>=? and l.data<? "
            "order by l.data, l.id", (ini.isoformat(), fim.isoformat())):
        g = grupos.setdefault(r["empresa_id"], {"empresa_id": r["empresa_id"], "empresa": r["nome"], "total_centavos": 0, "itens": []})
        g["total_centavos"] += r["valor"]
        g["itens"].append({"lancamento_id": r["id"], "data": r["data"], "descricao": r["descricao_original"], "valor_centavos": r["valor"]})
    return sorted(grupos.values(), key=lambda g: (-g["total_centavos"], g["empresa_id"]))
