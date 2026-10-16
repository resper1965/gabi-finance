"""Fechamento do dia (H3), sem modelo: gastos de hoje (total e os 3 maiores), baixas confirmadas hoje e o que ficou atrasado.
Só contas liberadas. Só lê; o texto sai pronto para o celular (até 5 linhas) e vazio de movimento vira uma frase só.
Consome: lancamento, conta, contas_pagar."""
import datetime as dt

from gabi.dinheiro import contas_pagar
from gabi.dinheiro.agenda_financeira import _brl

SEM_MOVIMENTO = "Sem movimento relevante."
TOP = 3


def _gastos(con, hoje: dt.date) -> tuple[int, int, list[tuple[str, int]]]:
    por: dict[str, int] = {}
    n = total = 0
    for r in con.execute(
            "select coalesce(l.estabelecimento, l.descricao_original, '?') as nome, -l.valor_centavos as gasto from lancamento l join conta c on c.id=l.conta_id "
            "where c.estado='sim' and c.excluido_em is null and l.natureza like '%custo%' and l.valor_centavos<0 and l.status='posted' and l.data=?", (hoje.isoformat(),)):
        por[r["nome"]] = por.get(r["nome"], 0) + r["gasto"]
        n, total = n + 1, total + r["gasto"]
    return n, total, sorted(por.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]


def montar(con, hoje: dt.date) -> list[str]:
    n, total, top = _gastos(con, hoje)
    g = contas_pagar.contas_a_pagar(con, hoje, hoje)
    pagas = [i for i in g["pagas"] if (i.get("pago_em") or "")[:10] == hoje.isoformat()]
    atrasadas = g["atrasadas"]
    if not n and not pagas and not atrasadas:
        return [SEM_MOVIMENTO]
    linhas = ["🌙 *Fechamento do dia*"]
    linhas.append(f"• Gastos: {_brl(total)} em {n} lançamento(s)" + (": " + "; ".join(f"{nome} {_brl(v)}" for nome, v in top) if top else ""))
    if pagas:
        linhas.append(f"• Pagas hoje: {len(pagas)} ({_brl(sum(i['valor_centavos'] or 0 for i in pagas))})")
    if atrasadas:
        linhas.append(f"• ⚠️ Atrasadas: {len(atrasadas)} ({_brl(sum(i['valor_centavos'] or 0 for i in atrasadas))})")
    return linhas
