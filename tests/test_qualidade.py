import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.qualidade import aceite, custo_por_tarefa, latencia

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "q.db")
    migrar(c, MIGR)
    return c


def sug(con, tipo, estado, quando="2026-10-10T10:00:00"):
    con.execute("insert into sugestao(tipo, payload, estado, criado_em) values (?,?,?,?)", (tipo, "{}", estado, quando))


def test_taxa_de_aceite_ignora_pendentes_e_o_que_passou_da_janela(con):
    for e in ("aprovada", "aprovada", "aprovada", "rejeitada", "pendente"):
        sug(con, "categoria", e)
    sug(con, "categoria", "rejeitada", "2026-01-01T00:00:00")  # velha demais
    sug(con, "regra", "rejeitada")
    a = aceite(con, HOJE)
    cat = next(s for s in a["sugestoes"] if s["tipo"] == "categoria")
    assert (cat["aprovadas"], cat["rejeitadas"], cat["pendentes"], cat["taxa_aceite"]) == (3, 1, 1, 0.75)
    assert next(s for s in a["sugestoes"] if s["tipo"] == "regra")["taxa_aceite"] == 0.0 and a["taxa_aceite_geral"] == 0.6


def test_sem_sugestao_decidida_a_taxa_e_nula_nao_zero(con):
    sug(con, "categoria", "pendente")
    assert aceite(con, HOJE)["taxa_aceite_geral"] is None


def test_perguntas_do_canal_por_estado(con):
    for estado in ("aberta", "respondida", "respondida", "expirada"):
        con.execute("insert into pergunta(tipo, titulo, opcoes, estado, criada_em, origem) values ('t','x','[]',?,'2026-10-12T10:00:00','claude')", (estado,))
    assert aceite(con, HOJE)["perguntas"] == {"respondidas": 2, "expiradas": 1, "abertas": 1}


def test_custo_por_tarefa_soma_e_ordena_do_mais_caro(con):
    for em, usd, t in [("2026-10-10", 0.02, "classificar"), ("2026-10-11", 0.03, "classificar"), ("2026-10-12", 0.10, "escuta"), ("2026-08-01", 5.0, "velho"), ("2026-10-13", 0.01, None)]:
        con.execute("insert into custo_modelo(em, custo_usd, tarefa) values (?,?,?)", (em, usd, t))
    c = custo_por_tarefa(con, HOJE)
    assert [t["tarefa"] for t in c["tarefas"]] == ["escuta", "classificar", "(sem tarefa)"] and c["total_usd"] == 0.16
    assert c["tarefas"][1]["chamadas"] == 2 and c["tarefas"][1]["medio_usd"] == 0.025


def test_latencia_mediana_p95_e_erros_por_ferramenta(con):
    for ms in [100, 110, 120, 130, 900]:
        con.execute("insert into chamada_mcp(quando, ferramenta, escopo, status, duracao_ms) values ('2026-10-15T10:00:00','agenda_financeira','fin','ok',?)", (ms,))
    con.execute("insert into chamada_mcp(quando, ferramenta, escopo, status, duracao_ms) values ('2026-10-15T10:00:00','agenda_financeira','fin','erro',50)")
    con.execute("insert into chamada_mcp(quando, ferramenta, escopo, status) values ('2026-10-15T10:00:00','agenda_financeira','fin','sem_escopo')")  # recusada: não conta
    con.execute("insert into chamada_mcp(quando, ferramenta, escopo, status) values ('2026-10-15T10:00:00','financeiro_saldo','fin','ok')")  # antiga, sem duração
    l = {f["ferramenta"]: f for f in latencia(con, HOJE)["ferramentas"]}
    assert l["agenda_financeira"] == {"ferramenta": "agenda_financeira", "chamadas": 6, "erros": 1, "mediana_ms": 115, "p95_ms": 900}
    assert l["financeiro_saldo"]["mediana_ms"] is None and l["financeiro_saldo"]["p95_ms"] is None
