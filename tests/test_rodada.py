import pytest

from gabi.db import conectar, migrar
from gabi.rodada import registrar_rodada
from pathlib import Path

MIGRACOES = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_rodada_ok_grava_contagens_e_fim(con):
    with registrar_rodada(con, "open-finance") as r:
        r.lidos, r.novos, r.alterados = 10, 4, 1
    linha = con.execute("select * from rodada").fetchone()
    assert (linha["fonte"], linha["status"], linha["lidos"], linha["novos"], linha["alterados"]) == (
        "open-finance", "ok", 10, 4, 1)
    assert linha["fim"] is not None and linha["inicio"] <= linha["fim"] and linha["erro"] is None


def test_rodada_com_erro_grava_status_erro_e_relevanta(con):
    with pytest.raises(RuntimeError, match="banco caiu"):
        with registrar_rodada(con, "nibo"):
            raise RuntimeError("banco caiu")
    linha = con.execute("select status, erro, fim from rodada").fetchone()
    assert linha["status"] == "erro" and "banco caiu" in linha["erro"] and linha["fim"] is not None


def test_rodada_aparece_como_rodando_enquanto_executa(con):
    with registrar_rodada(con, "x"):
        assert con.execute("select status from rodada").fetchone()["status"] == "rodando"
