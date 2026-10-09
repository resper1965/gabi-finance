import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tools.comparar_agenda import comparar

MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _brain(con, id_, venc, centavos):
    con.execute("insert into compromisso(id, nome, vencimento, vencimento_util, valor_centavos, estado) values (?,?,?,?,?, 'previsto')",
                (id_, id_, venc, venc, centavos))


def _fin(tmp_path, **secoes):
    arq = tmp_path / "compromissos.json"
    arq.write_text(json.dumps({k: [{"id": i, "vencimento": v, "valor": val} for i, v, val in itens] for k, itens in secoes.items()}))
    return arq


def test_igual_nao_gera_divergencia(con, tmp_path):
    _brain(con, "aluguel:2026-10", "2026-10-05", 450000)
    _brain(con, "luz:2026-10", "2026-10-12", 31090)
    arq = _fin(tmp_path, atrasadas=[("aluguel:2026-10", "2026-10-05", 4500.0)], proximos_7_dias=[("luz:2026-10", "2026-10-12", 310.9)])
    assert comparar(con, arq, "2026-10") == []


def test_linha_so_de_um_lado_e_reportada(con, tmp_path):
    _brain(con, "aluguel:2026-10", "2026-10-05", 450000)
    _brain(con, "so-brain:2026-10", "2026-10-08", 1000)
    arq = _fin(tmp_path, atrasadas=[("aluguel:2026-10", "2026-10-05", 4500.0)], a_conferir=[("so-fin:2026-10", "2026-10-09", 20.0)])
    r = {d["linha"]: d for d in comparar(con, arq, "2026-10")}
    assert r["so-brain:2026-10"]["so_no_brain"] and not r["so-brain:2026-10"]["so_no_financeiro"]
    assert r["so-fin:2026-10"]["so_no_financeiro"] and not r["so-fin:2026-10"]["so_no_brain"]
    assert "aluguel:2026-10" not in r


def test_valor_diferente_e_reportado_com_os_dois_valores(con, tmp_path):
    _brain(con, "luz:2026-10", "2026-10-12", 31090)
    arq = _fin(tmp_path, proximos_7_dias=[("luz:2026-10", "2026-10-12", 320.5)])
    (d,) = comparar(con, arq, "2026-10")
    assert d["linha"] == "luz:2026-10" and d["valor_diferente"] == {"brain": 31090, "financeiro": 32050}


def test_item_de_outro_mes_ou_fora_da_janela_do_financeiro_nao_vira_divergencia(con, tmp_path):
    _brain(con, "agua:2026-09", "2026-09-10", 100)          # outro mês
    _brain(con, "iptu:2026-10", "2026-10-28", 100)          # depois da janela de 7 dias do financeiro
    arq = _fin(tmp_path, proximos_7_dias=[("luz:2026-10", "2026-10-12", 1.0)])
    _brain(con, "luz:2026-10", "2026-10-12", 100)
    assert comparar(con, arq, "2026-10") == []
