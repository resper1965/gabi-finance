"""Moeda estrangeira: valor_centavos é sempre em reais (amountInAccountCurrency); o original fica em colunas próprias."""
import datetime as dt
from pathlib import Path

import pytest

from gabi.avisos import gerar_avisos
from gabi.db import conectar, migrar
from gabi.dinheiro.consultas import SQL_LANCAMENTO, lancamento_dict
from tests.dinheiro.test_captura import AGORA, BANCO, CARTAO, FakeFin, _lancs, _rodar, tx

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _usd(i="u1", tipo="DEBIT", **extra):
    return tx(i, "2026-10-07", "LOJA EXTERIOR", "6.01", tipo=tipo, currencyCode="USD", amountInAccountCurrency="31.32", **extra)


def _rodar_cartao(con, tmp_path, itens):
    _rodar(con, FakeFin([CARTAO], {"acc-card-9999": itens}), tmp_path)
    return _lancs(con)


def test_usd_com_conversao_grava_reais_e_original(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [_usd()])["u1"]
    assert (L["valor_centavos"], L["moeda"], L["valor_original_centavos"], L["convertido"]) == (-3132, "USD", -601, 1)


def test_debito_negativo_e_estorno_positivo(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [_usd("d"), _usd("e", tipo="CREDIT")])
    assert (L["d"]["valor_centavos"], L["d"]["valor_original_centavos"]) == (-3132, -601)
    assert (L["e"]["valor_centavos"], L["e"]["valor_original_centavos"]) == (3132, 601)


def test_brl_inalterado_moeda_e_original_nulos(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("b1", "2026-10-07", "PADARIA", 35.5, currencyCode="BRL", amountInAccountCurrency="35.50"),
                                      tx("b2", "2026-10-07", "MERCADO", 10.0)])
    for k in ("b1", "b2"):
        assert (L[k]["moeda"], L[k]["valor_original_centavos"], L[k]["convertido"]) == (None, None, 1)
    assert (L["b1"]["valor_centavos"], L["b2"]["valor_centavos"]) == (-3550, -1000)


def test_estrangeira_sem_conversao_grava_original_e_avisa_so_contagem(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("s1", "2026-10-07", "LOJA SECRETA", "6.01", currencyCode="EUR")])["s1"]
    assert (L["valor_centavos"], L["moeda"], L["valor_original_centavos"], L["convertido"]) == (-601, "EUR", -601, 0)
    gerar_avisos(con, AGORA)
    a = con.execute("select tipo, payload from aviso where tipo='lancamento_sem_conversao'").fetchall()
    assert len(a) == 1
    import json
    p = json.loads(a[0]["payload"])
    assert p["quantidade"] == 1 and "LOJA" not in a[0]["payload"] and "6.01" not in a[0]["payload"]
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='lancamento_sem_conversao'").fetchone()[0] == 1
    from gabi.rotas.avisos import descrever
    assert descrever("lancamento_sem_conversao", p)[0].startswith("Compra em moeda estrangeira sem valor em reais")


def test_sem_estrangeiros_sem_conversao_nao_avisa(con, tmp_path):
    _rodar_cartao(con, tmp_path, [_usd()])
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='lancamento_sem_conversao'").fetchone()[0] == 0


def test_reprocessar_corrige_linha_antiga_errada(con, tmp_path):
    _rodar_cartao(con, tmp_path, [_usd()])
    con.execute("update lancamento set valor_centavos=-601, moeda=null, valor_original_centavos=null where externo_id='u1'")
    (tmp_path / "outra").mkdir()
    L = _rodar_cartao(con, tmp_path / "outra", [_usd()])  # outra pasta de bruto: o arquivo do mesmo rótulo é imutável
    assert (L["u1"]["valor_centavos"], L["u1"]["moeda"], L["u1"]["valor_original_centavos"], L["u1"]["convertido"]) == (-3132, "USD", -601, 1)
    assert con.execute("select count(*) from lancamento").fetchone()[0] == 1


@pytest.mark.parametrize("ruim", ["abc", "", None, "nan", "inf"])
def test_conversao_invalida_vira_ausente(con, tmp_path, ruim):
    L = _rodar_cartao(con, tmp_path, [tx("x", "2026-10-07", "LOJA", "6.01", currencyCode="USD", amountInAccountCurrency=ruim)])["x"]
    assert (L["valor_centavos"], L["convertido"], L["moeda"]) == (-601, 0, "USD")


def test_conversao_negativa_em_debito_nao_derruba_e_fica_negativa(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("n", "2026-10-07", "LOJA", "6.01", currencyCode="USD", amountInAccountCurrency="-31.32")])["n"]
    assert (L["valor_centavos"], L["convertido"]) == (-3132, 1)


def test_api_traz_moeda_so_quando_estrangeira(con, tmp_path):
    _rodar_cartao(con, tmp_path, [_usd(), tx("b", "2026-10-07", "PADARIA", 5.0)])
    d = {r["externo_id"]: lancamento_dict(r) for r in con.execute(SQL_LANCAMENTO)}
    assert d["u1"]["valor"] == "-31.32" and d["u1"]["moeda"] == "USD" and d["u1"]["valor_original"] == "-6.01" and d["u1"]["convertido"] is True
    assert "moeda" not in d["b"] and "valor_original" not in d["b"]


def _historico_errado(con, tmp_path):
    """Banco com a captura antiga: valor original gravado como reais, e o bruto imutável no disco."""
    _rodar_cartao(con, tmp_path, [_usd(), tx("b", "2026-10-07", "PADARIA", 5.0)])
    con.execute("update lancamento set valor_centavos=-601, moeda=null, valor_original_centavos=null where externo_id='u1'")


def _snap(con):
    return [tuple(r) for r in con.execute("select externo_id, valor_centavos, moeda, valor_original_centavos, convertido from lancamento order by 1")]


def test_corrigir_moeda_dry_run_nao_altera_e_imprime_contagem(con, tmp_path, capsys):
    from tools.corrigir_moeda import corrigir
    _historico_errado(con, tmp_path)
    antes = _snap(con)
    r = corrigir(con, tmp_path / "bruto", dry_run=True)
    assert _snap(con) == antes
    assert (r["mudariam"], r["diferenca_centavos"]) == (1, -3132 + 601)
    capsys.readouterr()


def test_corrigir_moeda_corrige_e_e_idempotente(con, tmp_path):
    from tools.corrigir_moeda import corrigir
    _historico_errado(con, tmp_path)
    r = corrigir(con, tmp_path / "bruto")
    assert r["mudariam"] == 1
    L = _lancs(con)
    assert (L["u1"]["valor_centavos"], L["u1"]["moeda"], L["u1"]["valor_original_centavos"], L["u1"]["convertido"]) == (-3132, "USD", -601, 1)
    depois = _snap(con)
    r2 = corrigir(con, tmp_path / "bruto")
    assert r2["mudariam"] == 0 and r2["diferenca_centavos"] == 0 and _snap(con) == depois


def test_corrigir_moeda_cli_dry_run(con, tmp_path, capsys):
    from tools.corrigir_moeda import main
    _historico_errado(con, tmp_path)
    antes = _snap(con)
    con.close()
    assert main(["--dry-run", "--banco", str(tmp_path / "g.db"), "--bruto", str(tmp_path / "bruto")]) == 0
    out = capsys.readouterr().out
    assert "1" in out and "LOJA" not in out and "6.01" not in out
    c2 = conectar(tmp_path / "g.db")
    assert _snap(c2) == antes
