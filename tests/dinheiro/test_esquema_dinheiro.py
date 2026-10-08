import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _conta(con, externo="ext1"):
    return con.execute("insert into conta(externo_id, instituicao, tipo, apelido) values (?, 'C6', 'BANK', 'C6 PJ')",
                       (externo,)).lastrowid


def _lanc(con, conta_id, externo="l1", **extra):
    cols = {"conta_id": conta_id, "externo_id": externo, "data": "2026-10-08", "valor_centavos": -1000,
            "descricao_original": "PADARIA", "status": "posted", **extra}
    con.execute(f"insert into lancamento({','.join(cols)}) values ({','.join('?' * len(cols))})", list(cols.values()))


def test_0002_aplica_sobre_0001(con):
    nomes = [r[0] for r in con.execute("select nome from schema_versao order by nome")]
    assert nomes == ["0001_base.sql", "0002_dinheiro.sql"]
    tabelas = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"conta", "categoria", "equivalencia_categoria", "lancamento", "regra", "sugestao", "saldo", "conferencia",
            "assinatura"} <= tabelas


def test_conta_nasce_a_decidir(con):
    cid = _conta(con)
    assert con.execute("select estado from conta where id=?", (cid,)).fetchone()[0] == "a_decidir"


def test_conta_estado_invalido_rejeitado(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into conta(externo_id, estado) values ('x', 'talvez')")


def test_lancamento_externo_id_unico(con):
    cid = _conta(con)
    _lanc(con, cid)
    with pytest.raises(sqlite3.IntegrityError):
        _lanc(con, cid)


@pytest.mark.parametrize("coluna", ["categoria_origem", "para_quem_origem", "empresa_origem"])
def test_origem_invalida_rejeitada(con, coluna):
    cid = _conta(con)
    with pytest.raises(sqlite3.IntegrityError):
        _lanc(con, cid, **{coluna: "x"})


@pytest.mark.parametrize("origem", ["banco", "regra", "gabi", "voce", "fonte"])
def test_origens_validas_aceitas(con, origem):
    cid = _conta(con)
    _lanc(con, cid, categoria_origem=origem)


def test_lancamento_status_invalido_e_conta_inexistente(con):
    cid = _conta(con)
    with pytest.raises(sqlite3.IntegrityError):
        _lanc(con, cid, externo="s", status="talvez")
    with pytest.raises(sqlite3.IntegrityError):
        _lanc(con, 9999, externo="fk")


def test_valor_do_lancamento_e_inteiro(con):
    cid = _conta(con)
    _lanc(con, cid)
    assert con.execute("select typeof(valor_centavos) from lancamento").fetchone()[0] == "integer"


def test_regra_nasce_inativa(con):
    con.execute("insert into regra(padrao, acao, criado_em, criada_por) values ('UBER', '{}', '2026-10-08', 'gabi')")
    assert con.execute("select ativa from regra").fetchone()[0] == 0  # R1: só vale depois do Ricardo ligar


def test_sugestao_tipo_e_estado_validos(con):
    con.execute("insert into sugestao(tipo, payload, criado_em) values ('categoria', '{}', '2026-10-08')")
    assert con.execute("select estado from sugestao").fetchone()[0] == "pendente"
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into sugestao(tipo, payload, criado_em) values ('enviar_email', '{}', '2026-10-08')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into sugestao(tipo, payload, criado_em, estado) values ('regra', '{}', '2026-10-08', 'paga')")


def test_fatura_ganha_status_de_pagamento_sem_perder_colunas(con):
    cols = {r["name"] for r in con.execute("pragma table_info(fatura)")}
    assert {"id", "account_id", "vencimento", "total_centavos", "minimo_centavos", "pagamento_status", "conta_id"} <= cols


def test_conferencia_tipo_valido(con):
    cid = _conta(con)
    con.execute("insert into rodada(fonte, inicio, status) values ('open-finance','2026-10-08','ok')")
    con.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, criado_em) values (1,'saldo_final',?,1,'2026-10-08')", (cid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, criado_em) values (1,'qualquer',?,1,'2026-10-08')", (cid,))


def test_categoria_nome_unico_e_equivalencia(con):
    con.execute("insert into categoria(nome) values ('Mercado')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into categoria(nome) values ('Mercado')")
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Groceries', 1)")


def test_assinatura_status_valido(con):
    con.execute("insert into assinatura(estabelecimento) values ('NETFLIX')")
    assert con.execute("select status, lembrar_ate_cancelar from assinatura").fetchone()[:] == ("a_conferir", 0)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into assinatura(estabelecimento, status) values ('X', 'talvez')")
