"""Rumo (T4.3): mês a mês, quanto entrou, quanto saiu, quanto sobrou, quanto se gastou (e com quem/em qual frente) e qual é o patrimônio. Só SQL, sem DuckDB (ADR-004).
- entradas/saídas/poupança: lançamentos de natureza 'caixa' (inclui 'caixa+custo') das contas LIBERADAS (estado 'sim'), como o caixa único.
- gasto: `natureza like '%custo%'`, a mesma definição da tela Gastos (consultas.custos), por pessoa (`para_quem`) e por frente.
- patrimônio: soma do último saldo de cada conta BANK liberada até o fim do mês; None enquanto não houver nenhum saldo.
Valores em centavos inteiros (R7). Consome: lancamento, conta, saldo."""
import calendar
from dataclasses import dataclass, field

SEM_PESSOA, SEM_FRENTE = "(sem pessoa)", "(sem frente)"


@dataclass
class LinhaRumo:
    mes: str
    entradas: int = 0
    saidas: int = 0
    poupanca: int = 0
    gasto: int = 0
    patrimonio: int | None = None
    por_pessoa: dict = field(default_factory=dict)
    por_frente: dict = field(default_factory=dict)


def rumo_mensal(con, ano: int) -> list[LinhaRumo]:
    linhas = {f"{ano}-{m:02d}": LinhaRumo(f"{ano}-{m:02d}") for m in range(1, 13)}
    ini, fim = f"{ano}-01-01", f"{ano}-12-31"
    for r in con.execute(
            "select substr(l.data,1,7) mes, sum(case when l.valor_centavos>0 then l.valor_centavos else 0 end) e, "
            "sum(case when l.valor_centavos<0 then -l.valor_centavos else 0 end) s from lancamento l join conta c on c.id=l.conta_id "
            "where c.estado='sim' and l.natureza like '%caixa%' and l.data>=? and l.data<=? group by 1", (ini, fim)):
        l = linhas[r["mes"]]
        l.entradas, l.saidas, l.poupanca = r["e"], r["s"], r["e"] - r["s"]
    for r in con.execute("select substr(data,1,7) mes, -valor_centavos g, para_quem_id p, frente_id f from lancamento "
                         "where natureza like '%custo%' and data>=? and data<=?", (ini, fim)):
        l = linhas[r["mes"]]
        l.gasto += r["g"]
        p, f = r["p"] or SEM_PESSOA, str(r["f"]) if r["f"] is not None else SEM_FRENTE
        l.por_pessoa[p] = l.por_pessoa.get(p, 0) + r["g"]
        l.por_frente[f] = l.por_frente.get(f, 0) + r["g"]
    for mes, l in linhas.items():
        fim_mes = f"{mes}-{calendar.monthrange(ano, int(mes[5:]))[1]:02d}T23:59:59"
        soma = con.execute(
            "select sum(s.saldo_centavos), count(*) from saldo s join conta c on c.id=s.conta_id where c.estado='sim' and c.tipo='BANK' "
            "and s.em=(select max(em) from saldo where conta_id=s.conta_id and em<=?) and s.em<=?", (fim_mes, fim_mes)).fetchone()
        l.patrimonio = soma[0] if soma[1] else None
    return list(linhas.values())
