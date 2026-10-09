import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.previsao import previsao
from gabi.db import conectar, migrar

HOJE = dt.date(2026, 10, 9)
MIGR = Path(__file__).parent.parent.parent / "migrations"
_n = iter(range(1, 10_000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def nf(con, tomador, venc, liquido, bruto=None, status="autorizada", pago=0, doc=None):
    i = next(_n)
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, tomador_doc, vencimento, valor_liquido_centavos, nibo_pago, importado_em, atualizado_em) "
                "values (?,?,?,?,?,?,?,?,?,?,?,?)", (f"n{i}", str(i), venc, status, bruto or liquido, tomador, doc or tomador, venc, liquido, pago, "x", "x"))


def _mes(r, mes):
    return next(m for m in r["meses"] if m["mes"] == mes)


def test_notas_a_vencer_somam_por_mes_so_autorizadas_nao_pagas(con):
    nf(con, "A", "2026-10-15", 366015, bruto=390000)
    nf(con, "B", "2026-10-25", 100000)
    nf(con, "C", "2026-10-20", 999900, status="cancelada")
    nf(con, "D", "2026-10-21", 888800, status="negada")
    nf(con, "E", "2026-10-22", 777700, pago=1)
    nf(con, "F", "2026-11-05", 200000)
    r = previsao(con, HOJE, meses=2, projetar=False)
    out = _mes(r, "2026-10")["a_vencer"]
    assert (out["qtd"], out["liquido_centavos"], out["bruto_centavos"]) == (2, 466015, 490000)
    assert _mes(r, "2026-11")["a_vencer"]["liquido_centavos"] == 200000
    assert [n["tomador"] for n in out["notas"]] == ["A", "B"]  # em ordem de vencimento


def test_vencidas_nao_baixadas_ficam_a_parte_e_as_antigas_sao_so_contadas(con):
    nf(con, "A", "2026-09-20", 100000)   # 19 dias: recente, a confirmar pelo extrato
    nf(con, "B", "2026-05-10", 500000)   # > 60 dias: provavelmente recebida e sem baixa no Nibo
    r = previsao(con, HOJE, meses=1, projetar=False)
    assert (r["a_confirmar"]["qtd"], r["a_confirmar"]["liquido_centavos"]) == (1, 100000)
    assert (r["antigas"]["qtd"], r["antigas"]["liquido_centavos"]) == (1, 500000)
    assert _mes(r, "2026-10")["a_vencer"]["qtd"] == 0  # nada disso entra na previsão do mês


def test_projeta_contrato_recorrente_pelo_ultimo_valor_e_dia(con):
    for mes, v in (("2026-07", 100000), ("2026-08", 110000), ("2026-09", 120000)):
        nf(con, "REC", f"{mes}-15", v)
    r = previsao(con, HOJE, meses=2)
    p = _mes(r, "2026-10")["projetado"]
    assert (p["qtd"], p["liquido_centavos"]) == (1, 120000)  # pelo ÚLTIMO valor, nunca mediana
    assert p["notas"][0]["vencimento"] == "2026-10-15" and p["notas"][0]["tomador"] == "REC"
    assert _mes(r, "2026-11")["projetado"]["liquido_centavos"] == 120000


def test_nao_projeta_quando_o_mes_ja_tem_nota_ou_o_contrato_nao_e_recorrente(con):
    for mes in ("2026-07", "2026-08", "2026-09"):
        nf(con, "JA", f"{mes}-10", 100000)
    nf(con, "JA", "2026-10-12", 100000)                      # já emitida em outubro
    for mes in ("2026-07", "2026-09"):                       # faltou agosto: não é recorrente
        nf(con, "FURO", f"{mes}-10", 50000)
    r = previsao(con, HOJE, meses=2)
    assert [n["tomador"] for n in _mes(r, "2026-10")["projetado"]["notas"]] == []
    assert [n["tomador"] for n in _mes(r, "2026-11")["projetado"]["notas"]] == ["JA"]


def test_dia_do_vencimento_respeita_o_fim_do_mes(con):
    for mes in ("2026-07", "2026-08", "2026-09"):
        nf(con, "FIM", f"{mes}-30", 100000)
    r = previsao(con, HOJE, meses=5)
    assert _mes(r, "2026-11")["projetado"]["notas"][0]["vencimento"] == "2026-11-30"
    assert _mes(r, "2027-02")["projetado"]["notas"][0]["vencimento"] == "2027-02-28"
