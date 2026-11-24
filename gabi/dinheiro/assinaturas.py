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


DIAS_REEMBOLSO = 366  # ao preencher "reembolso por", as cobranças dos últimos 12 meses também entram


def sincronizar_reembolso(con, hoje: dt.date) -> int:
    """Põe nas cobranças de cada assinatura com "reembolso por" a empresa dela (origem `regra`): as dos últimos 12 meses e as novas.
    Só preenche lançamento sem empresa; a marcação feita à mão (ou por outra regra) nunca muda. Quando a assinatura troca de empresa
    ou volta a pessoal, desfaz só o que ela mesma marcou (e que ninguém mexeu depois). Devolve quantos lançamentos mudaram.
    O chamador abre a transação."""
    n = 0
    for r in con.execute("select r.lancamento_id, r.empresa_id, a.empresa_id as atual from assinatura_reembolso r "
                         "join assinatura a on a.id=r.assinatura_id").fetchall():
        if r["atual"] != r["empresa_id"]:
            n += con.execute("update lancamento set empresa_id=null, empresa_origem=null where id=? and empresa_id=? and empresa_origem='regra'",
                             (r["lancamento_id"], r["empresa_id"])).rowcount
            con.execute("delete from assinatura_reembolso where lancamento_id=?", (r["lancamento_id"],))
    desde = (hoje - dt.timedelta(days=DIAS_REEMBOLSO)).isoformat()
    for a in con.execute("select id, estabelecimento, empresa_id from assinatura where empresa_id is not null").fetchall():
        for l in con.execute("select id from lancamento where (estabelecimento=? or descricao_original like ?) and valor_centavos<0 "
                             "and data>=? and empresa_id is null", (a["estabelecimento"], f"{a['estabelecimento']}%", desde)).fetchall():
            con.execute("update lancamento set empresa_id=?, empresa_origem='regra' where id=?", (a["empresa_id"], l["id"]))
            con.execute("insert or replace into assinatura_reembolso(lancamento_id, assinatura_id, empresa_id) values (?,?,?)",
                        (l["id"], a["id"], a["empresa_id"]))
            n += 1
    return n
