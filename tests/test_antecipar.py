"""olhar_a_frente (ADR-037): caixa que fica negativo, a receber atrasado, documentos e atividades que vencem. Só lê tabelas locais.
AGORA = 09/11/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import antecipar
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def test_banco_vazio_nao_tem_nada_a_dizer(con):
    r = antecipar.olhar_a_frente(con, AGORA)
    assert r == {"dias": 30, "caixa": None, "a_receber_atrasado": [], "documentos": [], "atividades_vencendo": [], "ha_alerta": False}


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


def test_documentos_30_dias_e_atividades_7_dias(con, monkeypatch):
    monkeypatch.setattr(antecipar.repositorio, "vencimentos", lambda con, hoje, meses: [
        {"documento_id": 1, "titular_nome": "Louise", "tipo": "passaporte", "data": "2026-11-20", "vencido": False},
        {"documento_id": 2, "titular_nome": "Ricardo", "tipo": "cnh", "data": "2027-02-01", "vencido": False}])
    for texto, vence in (("ligar contador", "2026-11-12"), ("longe", "2026-12-30"), ("sem data", None)):
        con.execute("insert into atividade(texto, vence_em, status, origem, criada_em) values (?,?, 'aberta','hermes','2026-11-01T00:00:00+00:00')",
                    (texto, f"{vence}T03:00:00+00:00" if vence else None))
    r = antecipar.olhar_a_frente(con, AGORA)
    assert [d["documento_id"] for d in r["documentos"]] == [1]
    assert [a["texto"] for a in r["atividades_vencendo"]] == ["ligar contador"]
    assert r["ha_alerta"] is True  # documento conta como alerta


def test_so_atividade_vencendo_nao_e_alerta_do_resumo(con):
    con.execute("insert into atividade(texto, vence_em, status, origem, criada_em) values ('x','2026-11-12T03:00:00+00:00','aberta','hermes','2026-11-01T00:00:00+00:00')")
    r = antecipar.olhar_a_frente(con, AGORA)
    assert r["atividades_vencendo"] and r["ha_alerta"] is False  # atividades já saem no resumo da atividade (07:00)


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
