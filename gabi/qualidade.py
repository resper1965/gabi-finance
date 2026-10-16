"""Qualidade da Gabi (EV5): quanto das sugestões o Ricardo aceita, quanto custa cada tarefa do modelo e quão rápida é cada ferramenta.
Só lê (sugestao, pergunta, custo_modelo, chamada_mcp). Janelas curtas e fixas; sem dado pessoal, só contagens, dólares e milissegundos."""
import datetime as dt
import statistics as st

JANELA_ACEITE_DIAS = 90
JANELA_CUSTO_DIAS = 30
JANELA_LATENCIA_DIAS = 7


def _desde(hoje: dt.date, dias: int) -> str:
    return (hoje - dt.timedelta(days=dias)).isoformat()


def _taxa(aprovadas: int, rejeitadas: int):
    decididas = aprovadas + rejeitadas
    return round(aprovadas / decididas, 3) if decididas else None


def aceite(con, hoje: dt.date) -> dict:
    """Sugestões por tipo (categoria, para_quem, regra...) e perguntas do canal. `taxa_aceite` = aprovadas / (aprovadas + rejeitadas); pendentes não contam."""
    por_tipo = []
    for r in con.execute("select tipo, sum(estado='aprovada') a, sum(estado='rejeitada') r, sum(estado='pendente') p from sugestao where criado_em>=? group by tipo order by tipo",
                         (_desde(hoje, JANELA_ACEITE_DIAS),)):
        por_tipo.append({"tipo": r["tipo"], "aprovadas": r["a"], "rejeitadas": r["r"], "pendentes": r["p"], "taxa_aceite": _taxa(r["a"], r["r"])})
    tot_a, tot_r = sum(t["aprovadas"] for t in por_tipo), sum(t["rejeitadas"] for t in por_tipo)
    perguntas = {r["estado"]: r["n"] for r in con.execute("select estado, count(*) n from pergunta where criada_em>=? group by estado", (_desde(hoje, JANELA_ACEITE_DIAS),))}
    return {"janela_dias": JANELA_ACEITE_DIAS, "sugestoes": por_tipo, "taxa_aceite_geral": _taxa(tot_a, tot_r),
            "perguntas": {"respondidas": perguntas.get("respondida", 0), "expiradas": perguntas.get("expirada", 0), "abertas": perguntas.get("aberta", 0)}}


def custo_por_tarefa(con, hoje: dt.date) -> dict:
    itens = [{"tarefa": r["tarefa"] or "(sem tarefa)", "chamadas": r["n"], "total_usd": round(r["t"], 4), "medio_usd": round(r["t"] / r["n"], 5)}
             for r in con.execute("select tarefa, count(*) n, sum(custo_usd) t from custo_modelo where em>=? group by tarefa order by t desc", (_desde(hoje, JANELA_CUSTO_DIAS),))]
    return {"janela_dias": JANELA_CUSTO_DIAS, "tarefas": itens, "total_usd": round(sum(i["total_usd"] for i in itens), 4)}


def _percentil(valores: list[int], p: float) -> int:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p * (len(ordenados) - 1)))]


def latencia(con, hoje: dt.date) -> dict:
    """Por ferramenta: chamadas, erros, mediana e p95 em ms (só chamadas que executaram e registraram a duração)."""
    dados: dict[str, dict] = {}
    for r in con.execute("select ferramenta, status, duracao_ms from chamada_mcp where quando>=? and ferramenta is not null and status in ('ok','erro')",
                         (_desde(hoje, JANELA_LATENCIA_DIAS),)):
        d = dados.setdefault(r["ferramenta"], {"chamadas": 0, "erros": 0, "ms": []})
        d["chamadas"] += 1
        d["erros"] += r["status"] == "erro"
        if r["duracao_ms"] is not None:
            d["ms"].append(r["duracao_ms"])
    itens = [{"ferramenta": f, "chamadas": d["chamadas"], "erros": d["erros"], "mediana_ms": round(st.median(d["ms"])) if d["ms"] else None,
              "p95_ms": _percentil(d["ms"], 0.95) if d["ms"] else None} for f, d in sorted(dados.items())]
    return {"janela_dias": JANELA_LATENCIA_DIAS, "ferramentas": itens}


def qualidade(con, hoje: dt.date) -> dict:
    return {"aceite": aceite(con, hoje), "custo": custo_por_tarefa(con, hoje), "latencia": latencia(con, hoje)}
