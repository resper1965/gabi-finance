"""Saldo projetado do caixa, dia a dia: saldo de hoje (contas BANK liberadas) + entradas previstas − saídas previstas. Consome:
contas_pagar (caixa_unico, faturas_abertas), cobrar.previsao, db (compromisso, fatura).

Saídas: compromissos aberto/atrasado (atrasados saem hoje) e débito automático (`forma`) no dia; fatura de cartão aberta só se ainda não
for um compromisso (não conta duas vezes). Entradas: SÓ o `a_vencer` e o `projetado` da previsão de NFS-e (valor líquido); nota vencida
e não baixada fica na fila de conferência e nunca entra aqui (o Nibo é defasado). Tudo em centavos inteiros (R7)."""
import datetime as dt
import json

from gabi.cobrar.previsao import previsao
from gabi.dinheiro import contas_pagar

SAIDA_COM_ATRASO = {"aberto", "atrasado"}   # vencidos viram saída de hoje; débito automático (`forma`) só no dia, já debitado se a data passou


def projetar(con, hoje: dt.date, dias: int = 30) -> list[dict]:
    fim = hoje + dt.timedelta(days=dias)
    entradas: dict[dt.date, int] = {}
    saidas: dict[dt.date, int] = {}

    def somar(d: dict, dia: dt.date, v: int) -> None:
        if hoje <= dia < fim:
            d[dia] = d.get(dia, 0) + v

    ids = set()  # faturas que já estão contadas como compromisso (id `fatura:...` ou linha da planilha que reivindicou o cartão)
    for c in con.execute("select id, vencimento, valor_centavos, estado, forma, dados from compromisso"):
        if c["valor_centavos"] is None:
            continue
        ids.add(c["id"])
        try:
            cartao = json.loads(c["dados"] or "{}").get("cartao_account_id")
        except ValueError:
            cartao = None
        if cartao:
            ids.add(f"fatura:{cartao}:{c['vencimento'][:7]}")
        venc = dt.date.fromisoformat(c["vencimento"][:10])
        if c["estado"] in SAIDA_COM_ATRASO:
            if c["forma"] == "debito_automatico":
                if venc >= hoje:
                    somar(saidas, venc, c["valor_centavos"])
            else:
                somar(saidas, max(venc, hoje), c["valor_centavos"])
    for f in contas_pagar.faturas_abertas(con, hoje):
        conta = con.execute("select account_id from fatura where id=?", (f["id"],)).fetchone()
        if conta and f"fatura:{conta['account_id']}:{f['vencimento'][:7]}" in ids:
            continue
        somar(saidas, max(dt.date.fromisoformat(f["vencimento"][:10]), hoje), f["total_centavos"])

    for mes in previsao(con, hoje, meses=dias // 28 + 2)["meses"]:
        for bloco in ("a_vencer", "projetado"):
            for n in mes[bloco]["notas"]:
                somar(entradas, dt.date.fromisoformat(n["vencimento"]), n["liquido_centavos"] or 0)

    saldo = contas_pagar.caixa_unico(con, hoje).saldo_centavos
    saida = []
    for k in range(dias):
        d = hoje + dt.timedelta(days=k)
        saldo += entradas.get(d, 0) - saidas.get(d, 0)
        saida.append({"dia": d.isoformat(), "entradas_centavos": entradas.get(d, 0), "saidas_centavos": saidas.get(d, 0), "saldo_centavos": saldo})
    return saida
