import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from tests.dinheiro.cenarios import CASOS, carregar_cenario
from tools import comparar_conciliacao
from tools._conciliacao_antiga.fontes import rodar_antigo
from tools.comparar_conciliacao import comparar, main

MIGRACOES = Path(__file__).parent.parent / "migrations"
HOJE, AGORA = date(2026, 10, 8), datetime.fromisoformat("2026-10-08T15:00:00-03:00")


def _banco(caminho):
    c = conectar(caminho)
    migrar(c, MIGRACOES)
    carregar_cenario(c, next(x for x in CASOS if x["nome"] == "base")["entrada"])
    return c


@pytest.fixture
def con_cenario(tmp_path):
    return _banco(tmp_path / "g.db")


def test_comparacao_mostra_o_que_mudou(tmp_path):
    c = conectar(tmp_path / "j.db")
    migrar(c, MIGRACOES)
    carregar_cenario(c, next(x for x in CASOS if x["nome"] == "juros_e_a_menor")["entrada"])
    assert comparar(c, HOJE, AGORA) == [{"id": "condominio:2026-10", "nome": "Condomínio", "vencimento": "2026-10-08",
                                         "antes": "pago", "depois": "a_conferir", "tx_antes": "t8", "tx_depois": "t8",
                                         "motivo": "pago acima: R$ 840,00 de R$ 800,00"}]


def test_trocas_esperadas_nao_aparecem(monkeypatch, con_cenario):
    antigo = rodar_antigo(con_cenario, HOJE, AGORA)
    assert {v[2] for v in antigo.values()} & {"previsto", "debito_automatico"}  # o cenário base tem os dois
    novo = {k: (n, v, "aberto" if e in ("previsto", "debito_automatico") else e, m, t) for k, (n, v, e, m, t) in antigo.items()}
    monkeypatch.setattr(comparar_conciliacao, "_rodar_novo", lambda *a: novo)
    assert comparar(con_cenario, HOJE, AGORA) == []


def test_estado_que_muda_aparece(monkeypatch, con_cenario):
    antigo = rodar_antigo(con_cenario, HOJE, AGORA)
    cid, (n, v, e, m, t) = next((k, x) for k, x in antigo.items() if x[2] == "pago")
    monkeypatch.setattr(comparar_conciliacao, "_rodar_novo", lambda *a: {**antigo, cid: (n, v, "atrasado", None, None)})
    assert comparar(con_cenario, HOJE, AGORA) == [{"id": cid, "nome": n, "vencimento": v, "antes": "pago", "depois": "atrasado",
                                                   "tx_antes": t, "tx_depois": None, "motivo": None}]


def test_lancamento_que_muda_aparece(monkeypatch, con_cenario, capsys):
    antigo = rodar_antigo(con_cenario, HOJE, AGORA)
    cid, (n, v, e, m, t) = next((k, x) for k, x in antigo.items() if x[2] == "pago" and x[4])
    monkeypatch.setattr(comparar_conciliacao, "_rodar_novo", lambda *a: {**antigo, cid: (n, v, "pago", None, "outro")})
    assert comparar(con_cenario, HOJE, AGORA) == [{"id": cid, "nome": n, "vencimento": v, "antes": "pago", "depois": "pago",
                                                   "tx_antes": t, "tx_depois": "outro", "motivo": None}]
    comparar_conciliacao.imprimir(comparar(con_cenario, HOJE, AGORA))
    assert f"{cid} | {n} | {v} | pago({t}) → pago(outro) | " in capsys.readouterr().out


def test_main_le_o_banco_so_leitura(tmp_path, capsys):
    p = tmp_path / "g.db"
    c = _banco(p)
    c.commit()
    c.execute("pragma wal_checkpoint(truncate)")
    c.close()
    antes, mtime = p.read_bytes(), p.stat().st_mtime_ns
    assert main(["--banco", str(p), "--hoje", "2026-10-08"]) == 0
    assert "0 diferença(s)" in capsys.readouterr().out
    assert p.read_bytes() == antes and p.stat().st_mtime_ns == mtime
    ro = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    assert ro.execute("select count(*) from compromisso").fetchone()[0] == 0
    ro.close()
