import datetime as dt
import itertools
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.assinaturas import candidatas_por_categoria

HOJE = dt.date(2026, 10, 9)
_ids = itertools.count(1)
MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','CREDIT','sim')")
    c.execute("insert into categoria(nome) values ('Assinaturas e serviços digitais')")   # 1
    c.execute("insert into categoria(nome) values ('Mercado')")                          # 2
    return c


def _l(con, i, data, estab, valor, cat=1):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, categoria_id, natureza, status) "
                "values (1,?,?,?,?,?,?, 'custo', 'posted')", (f"l{i}", data, valor, estab, estab, cat))


def _mensal(con, estab, meses, valor=-5000, cat=1):
    for mes in meses:
        _l(con, next(_ids), f"{mes}-05", estab, valor, cat)


def _por_chave(lista):
    return {c["chave"]: c for c in lista}


def test_assinatura_de_categoria_com_dois_meses_distintos_entra(con):
    _mensal(con, "NETFLIX COM", ["2026-08", "2026-09", "2026-10"], -5990)
    r = _por_chave(candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], set()))
    n = r["NETFLIX COM"]
    assert (n["meses"], n["valor_medio"], n["ultimo"], n["ativa"]) == (3, 59.9, 59.9, True)


def test_compra_unica_ou_so_um_mes_nao_e_assinatura(con):
    _l(con, next(_ids), "2026-09-10", "LOJA UNICA", -9900)
    _l(con, next(_ids), "2026-09-20", "LOJA UNICA", -9900)   # duas cobranças no MESMO mês: não é recorrência mensal
    assert candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], set()) == []


def test_assinatura_que_parou_aparece_como_inativa(con):
    _mensal(con, "CLAUDE AI", ["2026-02", "2026-03", "2026-04"], -11685)
    c = _por_chave(candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], set()))["CLAUDE AI"]
    assert c["ativa"] is False


def test_so_categorias_da_lista_e_so_saidas(con):
    _mensal(con, "SUPERMERCADO", ["2026-08", "2026-09", "2026-10"], cat=2)
    _mensal(con, "REEMBOLSO", ["2026-08", "2026-09", "2026-10"], valor=5000)
    assert candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], set()) == []


def test_nao_repete_a_que_o_detector_ja_achou(con):
    _mensal(con, "SPOTIFY BR", ["2026-08", "2026-09", "2026-10"])
    assert candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], {"SPOTIFY BR"}) == []


def test_reajuste_usa_a_mediana_das_cobrancas_anteriores(con):
    for mes, v in (("2026-06", -4000), ("2026-07", -4000), ("2026-08", -4000), ("2026-09", -6000)):
        _l(con, next(_ids), f"{mes}-05", "STREAM X", v)
    c = _por_chave(candidatas_por_categoria(con, HOJE, ["Assinaturas e serviços digitais"], set()))["STREAM X"]
    assert (c["ultimo"], c["mediana_anterior"]) == (60.0, 40.0)


def test_categoria_inexistente_ou_lista_vazia_devolve_vazio(con):
    assert candidatas_por_categoria(con, HOJE, [], set()) == [] and candidatas_por_categoria(con, HOJE, ["Nao existe"], set()) == []
