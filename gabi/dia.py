"""Bloco dinheiro do dia: lê SÓ de tabelas prontas (nenhuma chamada de rede). Consome dinheiro.contas_pagar.
Veio de gabi/trabalho/hoje.py (ADR-023); no corte do gabi-finance saíram agenda, e-mail e prioridades: sobra o bloco `dinheiro`."""
import datetime as dt

from gabi.dinheiro import contas_pagar as cp
from gabi.dinheiro.valor import formatar


def _dinheiro(con, hoje: dt.date) -> dict:
    g = cp.contas_a_pagar(con, hoje, hoje)
    soma = lambda itens: sum(i["valor_centavos"] or 0 for i in itens)  # noqa: E731
    caixa = cp.caixa_unico(con, hoje)
    return {"saldo": formatar(caixa.saldo_centavos), "atrasadas": {"n": len(g["atrasadas"]), "valor": formatar(soma(g["atrasadas"]))},
            "sai_hoje": formatar(soma(g["hoje"])), "pago_hoje": formatar(soma([i for i in g["pagas"] if (i.get("pago_em") or "")[:10] == hoje.isoformat()]))}


def hoje(con, agora: dt.datetime) -> dict:
    return {"dinheiro": _dinheiro(con, agora.date())}
