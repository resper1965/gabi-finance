"""Olhar à frente (ADR-037), parte financeira: o que vai virar problema nos próximos dias, só de tabelas locais (sem rede, sem modelo, sem gravar).
Caixa projetado que fica negativo e a receber atrasado há 10 dias ou mais. Veio de gabi/antecipar.py; documentos e atividades saíram no corte do gabi-finance.
Consome: dinheiro.projecao, cobrar.a_receber. O resumo da manhã só ganha o bloco quando há alerta."""
import datetime as dt
from zoneinfo import ZoneInfo

from gabi.cobrar.a_receber import a_receber_do_mes
from gabi.dinheiro.projecao import projetar

BRT = ZoneInfo("America/Sao_Paulo")
ATRASO_MINIMO_DIAS = 10


def _caixa(con, hoje: dt.date, dias: int) -> dict | None:
    serie = projetar(con, hoje, dias)
    negativos = [d for d in serie if d["saldo_centavos"] < 0]
    if not negativos:
        return None
    minimo = min(serie, key=lambda d: d["saldo_centavos"])
    return {"primeiro_dia_negativo": negativos[0]["dia"], "saldo_minimo_centavos": minimo["saldo_centavos"], "dia_do_minimo": minimo["dia"]}


def _atrasados(con, hoje: dt.date) -> list[dict]:
    r = a_receber_do_mes(con, hoje)
    saida = []
    for i in r["recorrentes"]:
        if i["situacao"] == "atrasado" and (i["dias_atraso"] or 0) >= ATRASO_MINIMO_DIAS:
            saida.append({"pagador": i["pagador"], "valor_centavos": i["esperado_centavos"], "dias_atraso": i["dias_atraso"], "origem": "recorrente"})
    for n in r["notas"]:
        if n["situacao"] == "atrasado":
            dias = (hoje - dt.date.fromisoformat(n["vencimento"])).days
            if dias >= ATRASO_MINIMO_DIAS:
                saida.append({"pagador": n["pagador"], "valor_centavos": n["esperado_centavos"], "dias_atraso": dias, "origem": f"nota {n['numero']}"})
    return sorted(saida, key=lambda i: -i["dias_atraso"])


def olhar_a_frente(con, agora: dt.datetime, dias: int = 30) -> dict:
    hoje = agora.astimezone(BRT).date()
    caixa, atrasados = _caixa(con, hoje, dias), _atrasados(con, hoje)
    return {"dias": dias, "caixa": caixa, "a_receber_atrasado": atrasados, "ha_alerta": bool(caixa or atrasados)}


def _brl(centavos: int) -> str:
    sinal, c = ("-" if centavos < 0 else ""), abs(centavos)
    return f"{sinal}R$ {c // 100:,}".replace(",", ".") + f",{c % 100:02d}"


def _dm(iso: str) -> str:
    return dt.date.fromisoformat(iso[:10]).strftime("%d/%m")


def bloco_resumo(con, agora: dt.datetime) -> list[str]:
    r = olhar_a_frente(con, agora)
    if not r["ha_alerta"]:
        return []
    linhas = ["👀 *Olhando à frente*"]
    if r["caixa"]:
        c = r["caixa"]
        linhas.append(f"• Caixa fica negativo em {_dm(c['primeiro_dia_negativo'])}; pior ponto {_brl(c['saldo_minimo_centavos'])} em {_dm(c['dia_do_minimo'])}.")
    for i in r["a_receber_atrasado"][:3]:
        linhas.append(f"• {i['pagador']} está {i['dias_atraso']} dias atrasado ({_brl(i['valor_centavos'])}).")
    return linhas
