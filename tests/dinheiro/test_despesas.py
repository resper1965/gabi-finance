import datetime as dt
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import despesas
from tests.rotas.test_cadastros_api import banco, cli, req  # noqa: F401  (fixtures do cliente HTTP)

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


def test_cadastros_compromissos_continua(cli):
    r = req(cli, "POST", "/api/v1/cadastros/compromissos", {"nome": "X", "extrato": "X", "vencimento": "dia:40"})
    assert r.status_code == 400


def _avulsa(con, nome, data):
    return despesas.criar_avulsa(con, AGORA, "r", "painel", {"nome": nome, "valor_padrao": "100.00"}, data)


def test_avulsas_de_mesmo_nome_sao_series_distintas(con):
    a, b = _avulsa(con, "Dentista", "2026-11-20"), _avulsa(con, "Dentista", "2026-12-10")
    assert a["id"] != b["id"] and len(a["versoes"]) == len(b["versoes"]) == 1
    assert {i["id"] for i in despesas.listar(con, AGORA.date())} == {a["id"], b["id"]}


def test_avulsa_com_nome_de_fixa_existente(con):
    _fixa(con)
    av = _avulsa(con, "Escola", "2026-11-20")
    assert av["id"] != "escola" and av["tipo"] == "avulsa"
    assert [v["id"] for v in despesas.serie_de(con, "escola")] == ["escola"]


def test_fixa_depois_de_avulsa_de_mesmo_nome(con):
    _avulsa(con, "Dentista", "2026-11-20")
    f = despesas.criar_fixa(con, AGORA, "r", "painel", {"nome": "Dentista", "valor_padrao": "100.00", "vencimento": "dia:6"})
    assert f["tipo"] == "fixa" and f["id"] == "dentista-2"


def test_hoje_em_brt_mesmo_com_agora_em_utc(con):
    utc = dt.datetime(2026, 11, 1, 1, 0, tzinfo=dt.timezone.utc)  # 31/10 22:00 em Brasília
    despesas.criar_fixa(con, utc, "r", "painel", {"nome": "Luz", "valor_padrao": "10.00", "vencimento": "dia:6"})
    assert con.execute("select valido_de from compromisso_linha where id='luz'").fetchone()[0] == "2026-10"
