"""ADR-038: projeto ligado ao Linear (migração 0089, `projetos.ligar`, `projeto_parado` sem atividade do brain). Consome: gabi.projetos, gabi.atividades."""
import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from gabi import atividades, projetos
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
MIGR = Path(__file__).parent.parent / "migrations"
INICIO = dt.datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
URL = "https://linear.app/ricardo/project/fazenda-abc"


def em(dias):
    return INICIO + dt.timedelta(days=dias)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _ligar(con, linear_id="LIN-1", **kw):
    kw.setdefault("nome", "Vender a fazenda")
    return projetos.ligar(con, INICIO, "hermes", "hermes", linear_id, URL, **kw)


def test_migracao_acrescenta_colunas_e_linear_id_e_unico(con):
    cols = {r["name"] for r in con.execute("pragma table_info(projeto)")}
    assert {"linear_id", "linear_url"} <= cols
    for _ in range(2):  # dois sem linear_id convivem
        con.execute("insert into projeto(nome, criado_em, origem) values ('a','x','t')")
    con.execute("insert into projeto(nome, criado_em, origem, linear_id) values ('b','x','t','L')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into projeto(nome, criado_em, origem, linear_id) values ('c','x','t','L')")


def test_ligar_cria_a_pasta(con):
    r = _ligar(con)
    assert r["nome"] == "Vender a fazenda" and r["status"] == "ativo" and r["linear_id"] == "LIN-1" and r["linear_url"] == URL
    assert con.execute("select count(*) from decisao where o_que like 'projeto % ligado ao Linear%'").fetchone()[0] == 1
    assert projetos.listar(con, INICIO)[0]["linear_url"] == URL


def test_ligar_e_idempotente_por_linear_id(con):
    a = _ligar(con)
    b = _ligar(con, nome="Outro nome")
    assert a["id"] == b["id"] and b["nome"] == "Vender a fazenda"
    assert con.execute("select count(*) from projeto").fetchone()[0] == 1


def test_ligar_projeto_existente(con):
    p = projetos.criar(con, INICIO, "hermes", "hermes", "Reforma")["id"]
    r = projetos.ligar(con, INICIO, "hermes", "hermes", "LIN-9", URL, projeto_id=p)
    assert r["id"] == p and r["linear_id"] == "LIN-9" and r["nome"] == "Reforma"


def test_ligar_recusa_existente_ja_ligado_a_outro_id(con):
    p = _ligar(con)["id"]
    with pytest.raises(ValueError, match="já está ligado"):
        projetos.ligar(con, INICIO, "hermes", "hermes", "LIN-2", URL, projeto_id=p)


def test_ligar_recusa_projeto_final_e_inexistente(con):
    p = projetos.criar(con, INICIO, "hermes", "hermes", "Velho")["id"]
    projetos.atualizar(con, INICIO, "hermes", "hermes", p, status="cancelado")
    with pytest.raises(ValueError, match="não reabre|encerrado|cancelado"):
        projetos.ligar(con, INICIO, "hermes", "hermes", "LIN-3", URL, projeto_id=p)
    with pytest.raises(LookupError):
        projetos.ligar(con, INICIO, "hermes", "hermes", "LIN-4", URL, projeto_id=999)


@pytest.mark.parametrize("linear_id,url,nome", [("", URL, "x"), ("   ", URL, "x"), ("L", "", "x"), ("L", "http://linear.app/x", "x"), ("L", URL, "")])
def test_ligar_valida(con, linear_id, url, nome):
    with pytest.raises(ValueError):
        projetos.ligar(con, INICIO, "hermes", "hermes", linear_id, url, nome=nome)
    assert con.execute("select count(*) from projeto").fetchone()[0] == 0


def test_parado_com_linear_id_ignora_atividade_do_brain(con):
    liga = _ligar(con)["id"]
    sem = projetos.criar(con, INICIO, "hermes", "hermes", "Sem link", atividades=[{"texto": "x"}])["id"]
    atividades.criar(con, em(6), "hermes", "hermes", "nova", projeto_id=liga)
    atividades.criar(con, em(6), "hermes", "hermes", "nova2", projeto_id=sem)
    parados = {p["id"] for p in projetos.parados(con, em(8))}
    assert liga in parados and sem not in parados
    projetos.registrar_fato(con, em(7), "hermes", "hermes", liga, "combinado")
    assert liga not in {p["id"] for p in projetos.parados(con, em(8))}
    assert projetos.revalidar_aviso(con, {"id": liga, "ultimo_em": INICIO.isoformat()}) is False  # fato novo: o aviso antigo não vale mais
