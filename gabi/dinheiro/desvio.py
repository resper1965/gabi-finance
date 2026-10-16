"""Desvio do normal (AR8): um recorrente cujo valor deste mês foge do que ele costuma ser. Consome: analise (recorrentes), caixa.

Não altera `analise.recorrentes` (protegido por golden): usa a lista dele para saber o que é recorrente e relê as linhas para
medir o normal (média e desvio dos meses fechados anteriores). Só gera aviso; nunca decide nada."""
import datetime as dt
import statistics as st

from gabi.dinheiro import analise
from gabi.dinheiro.caixa import meses_atras, norm

MIN_MESES = 3      # meses fechados de histórico para ter um "normal"
DESVIOS = 2        # distância do normal, em desvios-padrão
PISO_REL = 0.10    # e pelo menos 10% do normal (série fixa tem desvio 0: 1 centavo não é aviso)


def fora_do_normal(fonte, hoje: dt.date | None = None) -> list[dict]:
    hoje = hoje or dt.date.today()
    ini = meses_atras(6, hoje).isoformat(); mes = hoje.strftime("%Y-%m")
    linhas: dict[tuple[str, int], list[dict]] = {}
    for r in fonte.visao("caixa", ini):
        if r["parcelas"] and r["parcelas"] > 1:
            continue
        linhas.setdefault((norm(r["descricao"]), 1 if r["valor"] > 0 else -1), []).append(r)
    out = []
    for rec in analise.recorrentes(fonte, "caixa", hoje):
        rs = linhas.get((rec["chave"].removesuffix(" OUTRO"), 1 if rec["sentido"] == "entrada" else -1))
        if rs and rec.get("faixa"):  # mesmo favorecido com dois pagamentos: compara só dentro da série (analise._series)
            lo, hi = rec["faixa"]
            rs = [r for r in rs if abs(r["valor"]) >= lo and (hi is None or abs(r["valor"]) < hi)]
        if not rs:
            continue
        por_mes: dict[str, float] = {}
        for r in rs:
            m = r["data"][:7]; por_mes[m] = max(por_mes.get(m, 0), abs(r["valor"]))
        antes = [v for m, v in por_mes.items() if m < mes]
        atual = por_mes.get(mes)
        if atual is None or len(antes) < MIN_MESES:
            continue
        normal = st.mean(antes); dp = st.pstdev(antes)
        if abs(atual - normal) > DESVIOS * dp and abs(atual - normal) > PISO_REL * normal:
            out.append({"descricao": rec["descricao"], "sentido": rec["sentido"], "valor": round(atual, 2), "normal": round(normal, 2),
                        "motivo": "valor_acima" if atual > normal else "valor_abaixo"})
    return out
