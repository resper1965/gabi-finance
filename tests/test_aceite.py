import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from tools.aceite import escrever_relatorio, medir_fase1

BRT = ZoneInfo("America/Sao_Paulo")
HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','BANK','sim')")
    c.execute("insert into categoria(nome) values ('Mercado')")
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    return c


def _rodada(con, dia: dt.date, hora_brt: int = 6, conferida: int = 1, fonte: str = "open-finance") -> int:
    fim = dt.datetime(dia.year, dia.month, dia.day, hora_brt, 0, tzinfo=BRT).astimezone(dt.timezone.utc).isoformat()
    return con.execute("insert into rodada(fonte, inicio, fim, status, conferida) values (?,?,?, 'ok', ?)", (fonte, fim, fim, conferida)).lastrowid


def test_conta_dias_seguidos_com_rodada_conferida_em_horario_de_brasilia(con):
    for k in range(7):
        _rodada(con, HOJE - dt.timedelta(days=k))
    _rodada(con, HOJE, hora_brt=23)  # 23h BRT = madrugada do dia seguinte em UTC: continua sendo o dia de Brasília
    r = medir_fase1(con, HOJE)
    assert r["dias_seguidos_conferidos"] == 7 and r["ultima_rodada_conferida"].startswith("2026-10-17T02")


def test_dia_sem_rodada_conferida_zera_a_sequencia(con):
    _rodada(con, HOJE - dt.timedelta(days=3))
    _rodada(con, HOJE - dt.timedelta(days=2), conferida=0)  # rodada existe mas não foi conferida
    _rodada(con, HOJE - dt.timedelta(days=1))
    _rodada(con, HOJE)
    assert medir_fase1(con, HOJE)["dias_seguidos_conferidos"] == 2


def test_hoje_ainda_sem_rodada_nao_zera_a_sequencia_de_ontem(con):
    for k in (1, 2, 3):
        _rodada(con, HOJE - dt.timedelta(days=k))
    assert medir_fase1(con, HOJE)["dias_seguidos_conferidos"] == 3


def test_so_conta_rodada_de_extrato(con):
    _rodada(con, HOJE, fonte="open-finance-saldos")
    assert medir_fase1(con, HOJE)["dias_seguidos_conferidos"] == 0


def test_saldo_final_reprovado_conta_so_dentro_da_sequencia(con):
    ok, ruim = _rodada(con, HOJE), _rodada(con, HOJE - dt.timedelta(days=30), conferida=0)
    for rid, v in ((ok, 1), (ruim, 0)):
        con.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, detalhe, criado_em) values (?, 'saldo_final', 1, ?, 'x', 'x')", (rid, v))
    assert medir_fase1(con, HOJE)["saldo_final_reprovado"] == 0


def test_classificado_exige_categoria_e_para_quem(con):
    def lanc(i, cat, pq):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_id, para_quem_id, status) values (1,?,?,?,?,?,?, 'posted')",
                    (f"l{i}", "2026-10-01", -100, "X", cat, pq))
    lanc(1, 1, "p1"); lanc(2, 1, None); lanc(3, None, "p1"); lanc(4, None, None)
    assert medir_fase1(con, HOJE)["classificado_pct"] == 0.25


def test_relatorio_lista_cada_criterio_com_data(con, tmp_path):
    _rodada(con, HOJE)
    saida = tmp_path / "aceite.md"
    escrever_relatorio(medir_fase1(con, HOJE), saida, HOJE)
    texto = saida.read_text(encoding="utf-8")
    for trecho in ("7 dias seguidos", "classificado", "2026-10-16", "saldo_final"):
        assert trecho in texto
