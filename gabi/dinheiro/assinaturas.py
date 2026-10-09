"""Assinaturas a revisar vindas de CATEGORIA (além das que o detector de recorrentes acha). Consome: db (lancamento, categoria).

O detector herdado do gabi-fin exige um padrão de cobrança que muitas assinaturas reais não cumprem (acha 7 de 64 lojas da
categoria). Aqui, uma loja de categoria de assinatura com cobrança em >= 2 meses distintos nos últimos 12 meses entra na lista;
a que não cobra há mais de 75 dias aparece como inativa (provavelmente cancelada), nunca some sozinha."""
import datetime as dt
import statistics

from gabi.dinheiro.caixa import norm

MESES_VISTOS = 12
DIAS_INATIVA = 75


def _mesmo(a: str, b: str) -> bool:
    a, b = norm(a)[:10], norm(b)[:10]
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def candidatas_por_categoria(con, hoje: dt.date, nomes: list[str], ja_detectadas: set[str]) -> list[dict]:
    if not nomes:
        return []
    ids = [r[0] for r in con.execute(f"select id from categoria where excluido_em is null and nome in ({','.join('?' * len(nomes))})", nomes)]
    if not ids:
        return []
    desde = (hoje - dt.timedelta(days=366)).isoformat()
    lojas: dict[str, list[tuple[str, float]]] = {}
    for r in con.execute(
            f"select data, valor_centavos, coalesce(estabelecimento, descricao_original) as loja from lancamento "
            f"where categoria_id in ({','.join('?' * len(ids))}) and valor_centavos<0 and data>=? and data<=? order by data",
            [*ids, desde, hoje.isoformat()]):
        if r["loja"]:
            lojas.setdefault(r["loja"], []).append((r["data"], -r["valor_centavos"] / 100))
    saida = []
    for loja, cobrancas in lojas.items():
        meses = {d[:7] for d, _ in cobrancas}
        if len(meses) < 2 or any(_mesmo(loja, d) for d in ja_detectadas):
            continue
        valores = [v for _, v in cobrancas]
        anteriores = valores[:-1]
        ultima = dt.date.fromisoformat(cobrancas[-1][0][:10])
        saida.append({"chave": loja, "descricao": loja, "valor_medio": round(statistics.mean(valores), 2), "meses": len(meses),
                      "ultimo": valores[-1], "mediana_anterior": statistics.median(anteriores) if len(anteriores) >= 2 else None,
                      "ativa": (hoje - ultima).days <= DIAS_INATIVA, "sentido": "saida"})
    return sorted(saida, key=lambda c: (not c["ativa"], -c["valor_medio"]))


def eh_habito(con, chave: str, categorias_habito: list[str]) -> bool:
    """A categoria dominante da loja (a de mais lançamentos) é de hábito de consumo (restaurante, mercado...): não é assinatura.
    Lista vazia ou loja sem lançamento: nunca é hábito (na dúvida a loja fica na lista para o Ricardo decidir)."""
    if not categorias_habito:
        return False
    r = con.execute(
        "select ca.nome, count(*) as n from lancamento l join categoria ca on ca.id=l.categoria_id "
        "where (l.estabelecimento=? or l.descricao_original like ?) and l.valor_centavos<0 group by ca.id order by n desc, ca.nome limit 1",
        (chave, f"{chave}%")).fetchone()
    return bool(r) and r["nome"] in categorias_habito
