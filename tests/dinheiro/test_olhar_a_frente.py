"""olhar_a_frente financeiro (ADR-037): caixa que fica negativo e a receber atrasado. Só lê tabelas locais.
Veio de tests/test_antecipar.py (as asserções de caixa e de a receber são as mesmas); documentos e atividades saíram no corte do gabi-finance.
AGORA = 09/11/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import olhar_a_frente as antecipar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def test_banco_vazio_nao_tem_nada_a_dizer(con):
    r = antecipar.olhar_a_frente(con, AGORA)
    assert r == {"dias": 30, "caixa": None, "a_receber_atrasado": [], "ha_alerta": False}


def test_caixa_negativo_acha_primeiro_dia_e_minimo(con, monkeypatch):
    base = dt.date(2026, 11, 9)
    serie = [{"dia": (base + dt.timedelta(days=k)).isoformat(), "entradas_centavos": 0, "saidas_centavos": 0, "saldo_centavos": s}
             for k, s in enumerate([500_00, 200_00, -100_00, -300_00, 50_00])]
    monkeypatch.setattr(antecipar, "projetar", lambda con, hoje, dias: serie)
    c = antecipar.olhar_a_frente(con, AGORA, dias=5)["caixa"]
    assert c == {"primeiro_dia_negativo": "2026-11-11", "saldo_minimo_centavos": -300_00, "dia_do_minimo": "2026-11-12"}


def test_caixa_sempre_positivo_vira_none(con, monkeypatch):
    serie = [{"dia": "2026-11-09", "entradas_centavos": 0, "saidas_centavos": 0, "saldo_centavos": 10}]
    monkeypatch.setattr(antecipar, "projetar", lambda con, hoje, dias: serie)
    assert antecipar.olhar_a_frente(con, AGORA)["caixa"] is None


def test_a_receber_atrasado_so_de_10_dias_ou_mais(con, monkeypatch):
    fake = {"recorrentes": [{"pagador": "FGV", "situacao": "atrasado", "esperado_centavos": 1000_00, "dias_atraso": 12},
                            {"pagador": "IONIC", "situacao": "atrasado", "esperado_centavos": 500_00, "dias_atraso": 3},
                            {"pagador": "NESS", "situacao": "recebido", "esperado_centavos": 700_00, "dias_atraso": 0}],
            "notas": [{"numero": 7, "pagador": "Bekaa", "situacao": "atrasado", "esperado_centavos": 200_00, "vencimento": "2026-10-20"},
                      {"numero": 8, "pagador": "ORM", "situacao": "atrasado", "esperado_centavos": 90_00, "vencimento": "2026-11-05"}]}
    monkeypatch.setattr(antecipar, "a_receber_do_mes", lambda con, hoje: fake)
    r = antecipar.olhar_a_frente(con, AGORA)
    assert [(i["pagador"], i["dias_atraso"]) for i in r["a_receber_atrasado"]] == [("Bekaa", 20), ("FGV", 12)]  # mais atrasado primeiro
    assert r["ha_alerta"] is True


def test_bloco_do_resumo_so_quando_ha_alerta(con, monkeypatch):
    assert antecipar.bloco_resumo(con, AGORA) == []
    monkeypatch.setattr(antecipar, "projetar", lambda con, hoje, dias: [
        {"dia": "2026-11-14", "entradas_centavos": 0, "saidas_centavos": 0, "saldo_centavos": -1234_56}])
    linhas = antecipar.bloco_resumo(con, AGORA)
    assert linhas[0].startswith("👀 *Olhando à frente*")
    assert any("14/11" in l and "R$ 1.234,56" in l for l in linhas)


def test_resumo_da_manha_mostra_o_bloco_e_sobrevive_a_falha(con, monkeypatch):
    from gabi.mcp.ferramentas_dia import resumo_da_manha
    monkeypatch.setattr(antecipar, "projetar", lambda con, hoje, dias: [
        {"dia": "2026-11-14", "entradas_centavos": 0, "saidas_centavos": 0, "saldo_centavos": -50_00}])
    assert any("Olhando à frente" in l for l in resumo_da_manha(con, AGORA)["linhas"])

    def quebra(con, agora):
        raise RuntimeError("boom")
    monkeypatch.setattr(antecipar, "bloco_resumo", quebra)
    linhas = resumo_da_manha(con, AGORA)["linhas"]
    assert linhas and not any("Olhando à frente" in l for l in linhas)
