"""Moeda estrangeira: valor_centavos é sempre em reais (amountInAccountCurrency); o original fica em colunas próprias."""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from gabi.avisos import gerar_avisos
from gabi.bruto import gravar_bruto
from gabi.db import conectar, migrar
from gabi.dinheiro.captura import capturar
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



# ---- sinal, zero, arredondamento, upsert do convertido

def test_cartao_credito_estorno_com_entrada_negativa_vira_positivo_nas_duas_colunas(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("r", "2026-10-07", "ESTORNO", "-6.01", tipo="CREDIT", currencyCode="USD", amountInAccountCurrency="-31.32")])["r"]
    assert (L["valor_centavos"], L["valor_original_centavos"]) == (3132, 601)


def test_conta_bank_com_tipo_credit_e_conversao_negativa_mesmo_sinal_nas_colunas(con, tmp_path):
    _rodar(con, FakeFin([BANCO], {"acc-bank-1111": [tx("k", "2026-10-07", "ESTORNO LOJA", "6.01", tipo="CREDIT", currencyCode="USD", amountInAccountCurrency="-31.32")]}), tmp_path)
    L = _lancs(con)["k"]
    assert (L["valor_centavos"], L["valor_original_centavos"], L["convertido"]) == (3132, 601, 1)


def test_conversao_zero_com_original_nao_zero_e_ausente_e_avisa(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("z", "2026-10-07", "LOJA", "6.01", currencyCode="USD", amountInAccountCurrency="0.00")])["z"]
    assert (L["valor_centavos"], L["convertido"]) == (-601, 0)
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='lancamento_sem_conversao'").fetchone()[0] == 1


def test_arredonda_meio_para_cima_na_string(con, tmp_path):
    L = _rodar_cartao(con, tmp_path, [tx("a", "2026-10-07", "LOJA", "6.01", currencyCode="USD", amountInAccountCurrency="31.325")])["a"]
    assert L["valor_centavos"] == -3133


def test_upsert_atualiza_convertido(con, tmp_path):
    _rodar_cartao(con, tmp_path, [_usd()])
    assert _lancs(con)["u1"]["convertido"] == 1
    (tmp_path / "outra").mkdir()
    sem = tx("u1", "2026-10-07", "LOJA EXTERIOR", "6.01", currencyCode="USD")
    L = _rodar_cartao(con, tmp_path / "outra", [sem])["u1"]
    assert (L["convertido"], L["valor_centavos"]) == (0, -601)


# ---- unificar pendente/lançado em moeda estrangeira

def _duas_rodadas(con, tmp_path, pend, post, hora=1):
    txs = {"acc-card-9999": [pend]}
    fin = FakeFin([CARTAO], txs)
    _rodar(con, fin, tmp_path)
    txs["acc-card-9999"] = [post] if not isinstance(post, list) else post
    capturar(con, FakeFin([CARTAO], txs), dt.date(2026, 10, 8), AGORA + dt.timedelta(hours=hora), tmp_path / "bruto")
    return _lancs(con)


def test_unifica_pending_usd_sem_conversao_com_posted_convertido(con, tmp_path):
    p = tx("p1", "2026-10-06", "LOJA EXTERIOR", "6.01", currencyCode="USD", status="PENDING")
    q = tx("q1", "2026-10-07", "LOJA EXTERIOR", "6.01", currencyCode="USD", amountInAccountCurrency="31.32", status="POSTED")
    L = _duas_rodadas(con, tmp_path, p, q)
    assert set(L) == {"q1"} and (L["q1"]["convertido"], L["q1"]["valor_centavos"]) == (1, -3132)


def test_unifica_pending_com_conversao_estimada_diferente(con, tmp_path):
    p = tx("p1", "2026-10-06", "LOJA EXTERIOR", "6.01", currencyCode="USD", amountInAccountCurrency="30.00", status="PENDING")
    q = tx("q1", "2026-10-07", "LOJA EXTERIOR", "6.01", currencyCode="USD", amountInAccountCurrency="31.32", status="POSTED")
    assert set(_duas_rodadas(con, tmp_path, p, q)) == {"q1"}


def test_compras_usd_diferentes_no_mesmo_dia_nao_unificam(con, tmp_path):
    p = tx("p1", "2026-10-06", "LOJA EXTERIOR", "6.01", currencyCode="USD", amountInAccountCurrency="31.32", status="PENDING")
    q = tx("q1", "2026-10-06", "LOJA EXTERIOR", "7.50", currencyCode="USD", amountInAccountCurrency="31.32", status="POSTED")
    assert set(_duas_rodadas(con, tmp_path, p, q)) == {"p1", "q1"}


# ---- ferramenta de correção

def _conta(con, tipo="CREDIT"):
    return con.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau',?, 'sim')", (tipo,)).lastrowid


def _lanc(con, cid, ext, valor, moeda=None, orig=None, conv=1):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, natureza, moeda, valor_original_centavos, convertido) "
                "values (?,?,?,?,?,?,?,?)", (cid, ext, "2026-10-07", valor, "custo", moeda, orig, conv))


def _raw(base, dia, rotulo, txs):
    gravar_bruto(base, "open-finance", dia, [{"conta": "c1", "tipo": "transacao", "dado": t} for t in txs], rotulo=rotulo)


def _snap(con):
    return [tuple(r) for r in con.execute("select externo_id, valor_centavos, moeda, valor_original_centavos, convertido from lancamento order by 1")]


def _cenario(con, tmp_path):
    base = tmp_path / "bruto"
    cid = _conta(con)
    _lanc(con, cid, "u1", -601)  # USD gravado errado (como reais)
    _lanc(con, cid, "b1", -1000)  # BRL ajustado depois; o bruto mais novo tem outro valor
    _raw(base, dt.date(2026, 10, 7), "a", [_usd("u1") | {"amountInAccountCurrency": "30.00"}, tx("b1", "2026-10-07", "PADARIA", 10.0)])
    _raw(base, dt.date(2026, 10, 8), "b", [_usd("u1"), tx("b1", "2026-10-07", "PADARIA", 99.0)])
    return base


def test_corrigir_dry_run_nao_altera_e_so_conta(con, tmp_path):
    from tools.corrigir_moeda import corrigir
    base = _cenario(con, tmp_path)
    antes = _snap(con)
    r = corrigir(con, base, dry_run=True)
    assert _snap(con) == antes and (r["mudariam"], r["diferenca_centavos"]) == (1, -3132 + 601)


def test_corrigir_usa_o_bruto_mais_novo_e_nao_toca_brl(con, tmp_path):
    from tools.corrigir_moeda import corrigir
    base = _cenario(con, tmp_path)
    assert corrigir(con, base)["mudariam"] == 1
    L = _lancs(con)
    assert (L["u1"]["valor_centavos"], L["u1"]["moeda"], L["u1"]["valor_original_centavos"], L["u1"]["convertido"]) == (-3132, "USD", -601, 1)
    assert (L["b1"]["valor_centavos"], L["b1"]["moeda"]) == (-1000, None)
    depois = _snap(con)
    r2 = corrigir(con, base)
    assert (r2["mudariam"], r2["diferenca_centavos"]) == (0, 0) and _snap(con) == depois


def test_corrigir_conta_sem_bruto(con, tmp_path):
    from tools.corrigir_moeda import corrigir
    base = _cenario(con, tmp_path)
    _lanc(con, _conta_id(con), "orfao", -500)
    assert corrigir(con, base, dry_run=True)["sem_bruto"] == 1


def _conta_id(con):
    return con.execute("select id from conta").fetchone()[0]


def test_corrigir_cli_dry_run_so_imprime_contagens(con, tmp_path, capsys):
    from tools.corrigir_moeda import main
    base = _cenario(con, tmp_path)
    antes = _snap(con)
    con.close()
    assert main(["--dry-run", "--banco", str(tmp_path / "g.db"), "--bruto", str(base)]) == 0
    out = capsys.readouterr().out
    assert "mudariam=1" in out and "LOJA" not in out and "6.01" not in out
    assert _snap(conectar(tmp_path / "g.db")) == antes


def test_corrigir_dry_run_nao_migra_banco_sem_0022(tmp_path, capsys):
    from tools.corrigir_moeda import main
    velhas = tmp_path / "migr"
    velhas.mkdir()
    for f in MIGRACOES.glob("*.sql"):
        if not f.name.startswith("0022"):
            shutil.copy(f, velhas / f.name)
    c = conectar(tmp_path / "v.db")
    migrar(c, velhas)
    c.close()
    assert main(["--dry-run", "--banco", str(tmp_path / "v.db"), "--bruto", str(tmp_path / "bruto")]) != 0
    assert "0022" in capsys.readouterr().out
    c = conectar(tmp_path / "v.db")
    assert "moeda" not in [r[1] for r in c.execute("pragma table_info(lancamento)")]
