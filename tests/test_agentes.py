import datetime as dt
import json
from pathlib import Path

import pytest

from gabi import agentes
from gabi.db import conectar, migrar
from gabi.mcp import tokens
from gabi.mcp.servidor import ESCOPOS_HERMES

MIGRACOES = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _n(con, tabela="token_agente"):
    return con.execute(f"select count(*) from {tabela}").fetchone()[0]


def test_criar_devolve_chave_uma_vez_e_usa_escopos_do_hermes(con):
    r = agentes.criar(con, AGORA, "ricardo", "Claude Code", None)
    assert r["chave"].startswith("gb_") and r["nome"] == "Claude Code"
    assert sorted(r["escopos"]) == sorted(ESCOPOS_HERMES)
    assert tokens.validar(con, r["chave"]).id == r["id"]
    assert not any("chave" in a for a in agentes.listar_agentes(con, AGORA))


def test_listar_nunca_devolve_segredo_nem_hash(con):
    r = agentes.criar(con, AGORA, "ricardo", "A", ["fin"])
    for a in agentes.listar_agentes(con, AGORA):
        assert "hash" not in a
        assert not any(isinstance(v, str) and v.startswith("gb_") for v in a.values())
        assert r["chave"] not in json.dumps(a)


def test_criar_rejeita_nome_vazio_e_escopo_invalido(con):
    with pytest.raises(ValueError):
        agentes.criar(con, AGORA, "r", "  ", ["fin"])
    with pytest.raises(ValueError):
        agentes.criar(con, AGORA, "r", "A", ["inexistente"])
    assert _n(con) == 0 and _n(con, "decisao") == 0


def test_trocar_escopos_nao_muda_segredo(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    it = agentes.trocar_escopos(con, AGORA, "r", r["id"], ["fin", "trabalho"])
    assert it["escopos"] == ["fin", "trabalho"] and "chave" not in it
    assert tokens.validar(con, r["chave"]).escopos == {"fin", "trabalho"}


def test_trocar_escopos_de_revogada_levanta_lookuperror(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    agentes.revogar_agente(con, AGORA, "r", r["id"])
    with pytest.raises(LookupError):
        agentes.trocar_escopos(con, AGORA, "r", r["id"], ["propostas"])


def test_revogar_faz_validar_devolver_none(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    it = agentes.revogar_agente(con, AGORA, "r", r["id"])
    assert it["ativo"] is False and tokens.validar(con, r["chave"]) is None


def test_rotacionar_revoga_antiga_e_emite_nova_com_mesmos_escopos(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin", "trabalho"])
    n = agentes.rotacionar(con, AGORA, "r", r["id"])
    assert n["id"] != r["id"] and n["nome"] == "A" and n["escopos"] == ["fin", "trabalho"] and n["chave"] != r["chave"]
    assert tokens.validar(con, r["chave"]) is None
    assert tokens.validar(con, n["chave"]).id == n["id"]


def test_rotacionar_atomico_se_emitir_falha(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    con.execute("update token_agente set escopo='lixo' where id=?", (r["id"],))
    with pytest.raises(ValueError):
        agentes.rotacionar(con, AGORA, "r", r["id"])
    assert _n(con) == 1 and con.execute("select revogado_em from token_agente").fetchone()[0] is None
    assert not con.in_transaction


def test_rotacionar_desfaz_a_nova_se_revogar_falha_depois_do_insert(con, monkeypatch):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    antes = _n(con, "decisao")

    def falha(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(agentes.tokens, "revogar", falha)
    with pytest.raises(RuntimeError):
        agentes.rotacionar(con, AGORA, "r", r["id"])
    assert _n(con) == 1 and tokens.validar(con, r["chave"]).id == r["id"]
    assert _n(con, "decisao") == antes and not con.in_transaction


def test_criar_desfaz_a_chave_se_falha_depois_do_insert(con, monkeypatch):
    def falha(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(agentes, "_auditar", falha)
    with pytest.raises(RuntimeError):
        agentes.criar(con, AGORA, "r", "A", ["fin"])
    assert _n(con) == 0 and _n(con, "decisao") == 0 and not con.in_transaction


def test_ultimo_uso_e_contagem_7d(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    for dias, h in ((10, 0), (3, 0), (1, 0)):
        q = (AGORA - dt.timedelta(days=dias, hours=h)).isoformat()
        con.execute("insert into chamada_mcp(quando, token_id, ferramenta, escopo, status) values (?,?,?,?,?)", (q, r["id"], "financeiro_saldo", "fin", "ok"))
    a = agentes.listar_agentes(con, AGORA)[0]
    assert a["chamadas_7d"] == 2 and a["ultimo_uso"] == (AGORA - dt.timedelta(days=1)).isoformat()


def test_chave_nunca_usada_tem_ultimo_uso_none_e_zero(con):
    agentes.criar(con, AGORA, "r", "A", ["fin"])
    a = agentes.listar_agentes(con, AGORA)[0]
    assert a["ultimo_uso"] is None and a["chamadas_7d"] == 0


def test_cada_operacao_grava_decisao_sem_segredo(con):
    r = agentes.criar(con, AGORA, "ricardo", "A", ["fin"])
    agentes.trocar_escopos(con, AGORA, "ricardo", r["id"], ["propostas"])
    n = agentes.rotacionar(con, AGORA, "ricardo", r["id"])
    agentes.revogar_agente(con, AGORA, "ricardo", n["id"])
    linhas = con.execute("select quem, o_que, origem from decisao order by id").fetchall()
    assert len(linhas) == 4 and all(l["origem"] == "agentes" and l["quem"] == "ricardo" for l in linhas)
    assert not any("gb_" in l["o_que"] for l in linhas)
    assert 'emitida' in linhas[0]["o_que"] and "escopos=propostas" in linhas[1]["o_que"] and f"nova {n['id']}" in linhas[2]["o_que"] and "revogada" in linhas[3]["o_que"]


def test_chamadas_de_revogada_continuam_visiveis(con):
    r = agentes.criar(con, AGORA, "r", "A", ["fin"])
    for i, q in enumerate(("2026-11-01T10:00:00+00:00", "2026-11-02T10:00:00+00:00")):
        con.execute("insert into chamada_mcp(quando, token_id, ferramenta, escopo, status) values (?,?,?,?,?)", (q, r["id"], f"f{i}", "fin", "ok"))
    agentes.revogar_agente(con, AGORA, "r", r["id"])
    c = agentes.chamadas(con, r["id"])
    assert [x["ferramenta"] for x in c] == ["f1", "f0"] and set(c[0]) == {"quando", "ferramenta", "status"}
    with pytest.raises(LookupError):
        agentes.chamadas(con, 999)


def test_conexao_usa_parametro_ou_padrao(con):
    c = agentes.conexao(con)
    assert c["url"].startswith("https://") and c["escopos_padrao"] == list(ESCOPOS_HERMES) and c["escopos_validos"] == sorted(tokens.ESCOPOS)
    con.execute("insert into parametro(chave, valor) values ('mcp.url', ?)", (json.dumps("https://x/mcp"),))
    assert agentes.conexao(con)["url"] == "https://x/mcp"
