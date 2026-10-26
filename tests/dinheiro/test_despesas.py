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


def test_migracao_tipo_e_dispensado(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('x','X','X','dia:5')")
    assert con.execute("select tipo from compromisso_linha where id='x'").fetchone()[0] == "fixa"
    con.execute("insert into valor_do_mes(mes, compromisso, tipo) values ('2026-10','x','dispensado')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update compromisso_linha set tipo='outra' where id='x'")


# ---------------- Task 2: criar e listar ----------------
import datetime as dt
from zoneinfo import ZoneInfo

from gabi.dinheiro import despesas

AGORA = dt.datetime(2026, 10, 26, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _fixa(con, **kw):
    return despesas.criar_fixa(con, AGORA, "ricardo", "painel", {"nome": "Escola", "valor_padrao": "3000.00", "vencimento": "dia:6", **kw})


def test_criar_fixa_gera_em_a_pagar(con):
    item = _fixa(con)
    assert item["id"] == "escola" and item["valor"] == "3000.00" and item["tipo"] == "fixa" and item["situacao"] == "ativa"
    ocs = dict(con.execute("select id, valor_centavos from compromisso where linha_id='escola'").fetchall())
    assert ocs["escola:2026-10"] == 300000 and ocs["escola:2026-11"] == 300000
    assert con.execute("select o_que, quem, origem from decisao").fetchone()[:] == ("despesa escola criada (fixa)", "ricardo", "painel")
    assert con.execute("select extrato, valido_de from compromisso_linha where id='escola'").fetchone()[:] == ("Escola", "2026-10")


def test_criar_avulsa_so_um_mes(con):
    item = despesas.criar_avulsa(con, AGORA, "ricardo", "hermes", {"nome": "Dentista", "valor_padrao": "450.00"}, "2026-11-20")
    assert item["id"] == "dentista" and item["versao_id"] == "dentista-202611" and item["tipo"] == "avulsa" and item["vencimento"] == "dia:20"
    r = con.execute("select tipo, valido_de, valido_ate from compromisso_linha where id='dentista-202611'").fetchone()
    assert r[:] == ("avulsa", "2026-11", "2026-11")
    ids = [x[0] for x in con.execute("select id from compromisso where linha_id like 'dentista%'")]
    assert ids and all(i.endswith(":2026-11") for i in ids)


def test_criar_invalido(con):
    with pytest.raises(ValueError):
        _fixa(con, vencimento="dia:40")
    with pytest.raises(ValueError):
        despesas.criar_fixa(con, AGORA, "r", "painel", {"nome": " "})
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == 0


def test_listar_por_tipo_e_situacao(con):
    _fixa(con)
    despesas.criar_avulsa(con, AGORA, "r", "painel", {"nome": "Dentista", "valor_padrao": "450.00"}, "2026-11-20")
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valido_ate) values ('velha','Velha','Velha','dia:5','2026-08')")
    todos = despesas.listar(con, AGORA.date())
    assert {i["id"] for i in todos} == {"escola", "dentista", "velha"}
    assert [i["id"] for i in despesas.listar(con, AGORA.date(), tipo="avulsa")] == ["dentista"]
    assert [i["id"] for i in despesas.listar(con, AGORA.date(), situacao="encerrada")] == ["velha"]
    esc = next(i for i in todos if i["id"] == "escola")
    assert esc["proximo_vencimento"] == "2026-11-06" and esc["versoes"][0]["id"] == "escola"
    with pytest.raises(LookupError):
        despesas.serie_de(con, "nada")


def test_cadastros_compromissos_continua():
    from gabi.rotas import cadastros
    from gabi.rotas.cadastros import COMPROMISSOS
    assert cadastros._slug("Água Ç") == "agua-c"
    with pytest.raises(Exception) as e:
        COMPROMISSOS._validar(None, {"id": "x", "nome": "X", "extrato": "X", "vencimento": "dia:40"}, None)
    assert getattr(e.value, "status_code", None) == 400
