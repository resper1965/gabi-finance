"""Perfil de 5 meses (PF1): para cada série recorrente, quão regular ela é. Consome: analise (recorrentes), caixa.

Só lê e classifica; não decide nada. Não altera `analise.recorrentes` (protegido por golden): usa a lista dele para saber o que é
recorrente e relê as linhas da mesma forma que `desvio.py` para medir presença, variação de valor e espalhamento do dia.
Classe: regular = presente em quase todos os meses fechados, valor e dia estáveis; semi = presente, mas valor ou dia oscilam; irregular = falta em mais de 20% dos meses.
Só classifica o que `analise.recorrentes` já aceita (presença em 3 dos últimos 4 meses); contrato de 2 meses fica com `esperados.py`."""
import datetime as dt
import statistics as st

from gabi.dinheiro import analise
from gabi.dinheiro.caixa import meses_atras, norm
from gabi.hoje import hoje_brt

MESES = 5                 # meses fechados olhados (o mês corrente não entra: está incompleto)
PRESENCA_MINIMA = 0.8     # fração dos meses fechados com a série presente; abaixo disso é irregular
CV_REGULAR = 0.15         # variação do valor (desvio/média) até aqui é estável
DIA_REGULAR = 3           # espalhamento do dia (desvio, em dias) até aqui é estável


def _classe(presenca: float, cv: float, dia_dp: float) -> str:
    if presenca < PRESENCA_MINIMA:
        return "irregular"
    return "regular" if cv <= CV_REGULAR and dia_dp <= DIA_REGULAR else "semi"


def perfil(fonte, hoje: dt.date | None = None) -> list[dict]:
    hoje = hoje or hoje_brt()
    mes_atual = hoje.strftime("%Y-%m")
    fechados = [meses_atras(i, hoje).strftime("%Y-%m") for i in range(1, MESES + 1)]
    linhas: dict[tuple[str, int], list[dict]] = {}
    for r in fonte.visao("caixa", meses_atras(MESES, hoje).isoformat()):
        if r["parcelas"] and r["parcelas"] > 1:
            continue
        linhas.setdefault((norm(r["descricao"]), 1 if r["valor"] > 0 else -1), []).append(r)
    out = []
    for rec in analise.recorrentes(fonte, "caixa", hoje):
        rs = linhas.get((rec["chave"].removesuffix(" OUTRO"), 1 if rec["sentido"] == "entrada" else -1))
        if rs and rec.get("faixa"):
            lo, hi = rec["faixa"]
            rs = [r for r in rs if abs(r["valor"]) >= lo and (hi is None or abs(r["valor"]) < hi)]
        rs = [r for r in (rs or []) if r["data"][:7] < mes_atual]
        if not rs:
            continue
        por_mes: dict[str, list[dict]] = {}
        for r in rs:
            por_mes.setdefault(r["data"][:7], []).append(r)
        primeiro = min(por_mes)
        janela = [m for m in fechados if m >= primeiro]  # mês anterior ao primeiro registro não conta como ausência
        if not janela:
            continue
        valores = [max(abs(r["valor"]) for r in v) for v in por_mes.values()]
        dias = [int(max(v, key=lambda r: abs(r["valor"]))["data"][8:10]) for v in por_mes.values()]
        media = st.mean(valores)
        cv = st.pstdev(valores) / media if len(valores) > 1 and media else 0.0
        dia_dp = st.pstdev(dias) if len(dias) > 1 else 0.0
        presenca = sum(m in por_mes for m in janela) / len(janela)
        out.append({"descricao": rec["descricao"], "sentido": rec["sentido"], "valor_medio": rec["valor_medio"], "dia_tipico": rec["dia"],
                    "meses_presentes": sum(m in por_mes for m in janela), "meses_janela": len(janela), "presenca": round(presenca, 2),
                    "variacao_valor": round(cv, 3), "espalhamento_dia": round(dia_dp, 1),
                    "classe": _classe(presenca, cv, dia_dp), "faixa": rec.get("faixa")})
    return sorted(out, key=lambda x: (x["sentido"] != "entrada", -x["valor_medio"]))
