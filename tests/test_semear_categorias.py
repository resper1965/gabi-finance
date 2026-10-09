from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tools.semear_categorias import aplicar

MIGR = Path(__file__).parent.parent / "migrations"
CSV = """categoria;grupo;equivale_nibo;origens_banco
Mercado;Pessoal;;Groceries
Telefonia e internet;Pessoal;Telefonia e Internet;Telecommunications|Internet
Movimentação interna (não é gasto);Pessoal;;Credit card payment|Transfer - Internal
"""


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into categoria(nome, nibo_category_id) values ('Telefonia e Internet', 'nibo-tel')")
    return c


@pytest.fixture
def arq(tmp_path):
    p = tmp_path / "cat.csv"
    p.write_text(CSV, encoding="utf-8")
    return p


def _mapa(con):
    return {r[0]: r[1] for r in con.execute("select e.origem_pluggy, c.nome from equivalencia_categoria e join categoria c on c.id=e.categoria_id")}


def test_cria_grupo_categorias_e_equivalencias(con, arq):
    r = aplicar(con, arq, "teste")
    assert (r.categorias_criadas, r.equivalencias_criadas, r.conflitos, r.nibo_nao_encontrados) == (4, 5, [], [])  # grupo + 3 categorias
    assert _mapa(con) == {"Groceries": "Mercado", "Telecommunications": "Telefonia e internet", "Internet": "Telefonia e internet",
                          "Credit card payment": "Movimentação interna (não é gasto)", "Transfer - Internal": "Movimentação interna (não é gasto)"}
    pai = con.execute("select p.nome from categoria c join categoria p on p.id=c.pai_id where c.nome='Mercado'").fetchone()[0]
    assert pai == "Pessoal"


def test_liga_ao_nibo_pelo_nome_da_categoria_do_nibo(con, arq):
    aplicar(con, arq, "teste")
    assert con.execute("select nibo_category_id from categoria where nome='Telefonia e internet'").fetchone()[0] == "nibo-tel"
    assert con.execute("select nibo_category_id from categoria where nome='Mercado'").fetchone()[0] is None


def test_e_idempotente_e_audita(con, arq):
    aplicar(con, arq, "teste")
    antes = con.execute("select count(*) from decisao").fetchone()[0]
    r = aplicar(con, arq, "teste")
    assert (r.categorias_criadas, r.equivalencias_criadas) == (0, 0)
    assert con.execute("select count(*) from decisao").fetchone()[0] == antes and antes > 0


def test_nao_sobrescreve_equivalencia_que_o_ricardo_ja_escolheu(con, arq):
    outra = con.execute("insert into categoria(nome) values ('Minha escolha')").lastrowid
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Groceries', ?)", (outra,))
    r = aplicar(con, arq, "teste")
    assert _mapa(con)["Groceries"] == "Minha escolha" and r.conflitos == ["Groceries"]


def test_nome_do_nibo_inexistente_e_reportado_e_a_categoria_fica_sem_id(con, tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("categoria;grupo;equivale_nibo;origens_banco\nImpostos;Pessoal;Taxas e contribuições;Taxes\n", encoding="utf-8")
    r = aplicar(con, p, "teste")
    assert r.nibo_nao_encontrados == ["Impostos -> Taxas e contribuições"] and _mapa(con) == {"Taxes": "Impostos"}


def test_arquivo_malformado_nao_grava_nada(con, tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("categoria;grupo\nMercado;Pessoal\n", encoding="utf-8")
    with pytest.raises(ValueError):
        aplicar(con, p, "teste")
    assert con.execute("select count(*) from categoria where nome='Pessoal'").fetchone()[0] == 0


def test_o_arquivo_de_seeds_do_projeto_e_valido_e_sem_origem_duplicada(con):
    seeds = Path(__file__).parent.parent / "seeds" / "categorias-pessoais.csv"
    r = aplicar(con, seeds, "teste")
    origens = [o for l in seeds.read_text(encoding="utf-8").splitlines()[1:] for o in l.split(";")[3].split("|") if o]
    assert len(origens) == len(set(origens)) and r.equivalencias_criadas == len(origens)
