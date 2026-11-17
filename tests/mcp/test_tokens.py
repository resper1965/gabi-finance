import hashlib
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.mcp.tokens import ESCOPOS, Token, _hash, definir_escopos, emitir, listar, revogar, validar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_emitir_devolve_o_token_uma_vez_e_guarda_so_o_hash(con):
    t = emitir(con, "hermes", ["fin", "trabalho"])
    assert t.startswith("gb_") and len(t) >= 40
    linha = con.execute("select * from token_agente").fetchone()
    assert linha["hash"] == hashlib.sha256(t.encode()).hexdigest() and t not in str(tuple(linha))
    assert linha["nome"] == "hermes" and linha["escopo"] == "fin,trabalho" and linha["revogado_em"] is None


def test_tokens_sao_unicos_e_aleatorios(con):
    assert emitir(con, "a", ["fin"]) != emitir(con, "b", ["fin"])


@pytest.mark.parametrize("escopos", [[], ["fin", "inventado"], ["FIN"], [""]])
def test_escopo_invalido_levanta(con, escopos):
    with pytest.raises(ValueError):
        emitir(con, "x", escopos)
    assert con.execute("select count(*) from token_agente").fetchone()[0] == 0


def test_nome_obrigatorio(con):
    with pytest.raises(ValueError):
        emitir(con, "  ", ["fin"])


def test_validar_token_valido(con):
    t = emitir(con, "hermes", ["fin", "trabalho"])
    v = validar(con, t)
    assert v == Token(id=1, nome="hermes", escopos=frozenset({"fin", "trabalho"}))


@pytest.mark.parametrize("ruim", ["", "gb_nao_existe", "lixo", None])
def test_validar_desconhecido_ou_vazio_devolve_none(con, ruim):
    emitir(con, "hermes", ["fin"])
    assert validar(con, ruim) is None


def test_token_revogado_nao_valida(con):
    t = emitir(con, "hermes", ["fin"])
    revogar(con, 1)
    assert validar(con, t) is None
    assert con.execute("select revogado_em from token_agente").fetchone()[0] is not None


def test_revogar_duas_vezes_ok_e_inexistente_levanta(con):
    emitir(con, "x", ["fin"])
    revogar(con, 1)
    revogar(con, 1)
    with pytest.raises(LookupError):
        revogar(con, 99)


def test_validar_nao_confunde_prefixo_do_token(con):
    t = emitir(con, "x", ["fin"])
    assert validar(con, t[:-1]) is None and validar(con, t + "x") is None


def test_listar_nunca_expoe_hash_nem_token(con):
    t = emitir(con, "hermes", ["fin"])
    revogar(con, emitir(con, "velho", ["propostas"]) and 2)
    itens = listar(con)
    assert [i["nome"] for i in itens] == ["hermes", "velho"] and itens[0]["ativo"] is True and itens[1]["ativo"] is False
    assert all("hash" not in i and t not in str(i) for i in itens)


def test_escopos_do_plano():
    assert ESCOPOS == {"fin", "trabalho", "pedidos", "propostas", "decisoes", "sensivel"}  # docs, envios, familia, contatos, atividades e projetos saíram com as ferramentas (corte)


def test_revogar_tudo_da_api_invalida_os_tokens(con):
    t = emitir(con, "hermes", ["fin"])
    con.execute("update token_agente set revogado_em=datetime('now') where revogado_em is null")  # o que /api/revogar-tudo faz
    assert validar(con, t) is None


def test_definir_escopos(con):
    t = emitir(con, "hermes", ["fin"])
    h = con.execute("select hash from token_agente").fetchone()[0]
    definir_escopos(con, 1, ["fin", "propostas"])
    assert validar(con, t).escopos == {"fin", "propostas"} and con.execute("select hash from token_agente").fetchone()[0] == h
    with pytest.raises(ValueError):
        definir_escopos(con, 1, ["x"])
    with pytest.raises(ValueError):
        definir_escopos(con, 1, [])
    with pytest.raises(LookupError):
        definir_escopos(con, 99, ["fin"])
    revogar(con, 1)
    with pytest.raises(LookupError):
        definir_escopos(con, 1, ["fin"])


def test_token_antigo_com_escopo_que_saiu_continua_valido(con):
    """O escopo some, o token não: quem emitiu `familia` ou `docs` antes do corte segue autenticando; só não alcança mais nenhuma ferramenta por ele."""
    con.execute("insert into token_agente(nome, escopo, hash, criado_em) values ('antigo', 'fin,familia,docs', ?, '2026-01-01T00:00:00+00:00')", (_hash("gb_antigo"),))
    v = validar(con, "gb_antigo")
    assert v is not None and v.escopos == frozenset({"fin", "familia", "docs"})
