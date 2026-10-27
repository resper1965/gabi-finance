"""Atividades (ADR-033): regras de criar, listar, concluir, cancelar e adiar. Consome: gabi.atividades. AGORA = 27/10/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import atividades
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 27, 15, 0, tzinfo=UTC)  # 12:00 em Brasília
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _criar(con, texto="ligar pro contador", vence=None, agora=AGORA):
    return atividades.criar(con, agora, "hermes", "hermes", texto, vence)


def test_criar_com_hora_guarda_utc_e_devolve_local(con):
    a = _criar(con, vence="2026-10-30T10:00")
    assert a["vence_em"] == "2026-10-30T10:00" and a["tem_hora"] is True and a["status"] == "aberta"
    assert con.execute("select vence_em from atividade where id=?", (a["id"],)).fetchone()[0] == "2026-10-30T13:00:00+00:00"
    d = con.execute("select quem, origem from decisao").fetchall()
    assert len(d) == 1 and tuple(d[0]) == ("hermes", "hermes")


def test_criar_so_data_vale_o_dia_todo(con):
    a = _criar(con, vence="2026-10-30")
    assert a["tem_hora"] is False and a["prazo"] == "proxima" and a["vence_em"] == "2026-10-30"
    assert _criar(con, "outra").get("prazo") == "sem_data"


def test_criar_recusa_passado(con):
    with pytest.raises(ValueError):
        _criar(con, vence="2026-10-26")
    with pytest.raises(ValueError):
        _criar(con, vence="2026-10-27T11:59")
    assert _criar(con, vence="2026-10-27")["prazo"] == "hoje"


def test_criar_recusa_texto_vazio_e_longo(con):
    for ruim in ("   ", "x" * 501):
        with pytest.raises(ValueError):
            _criar(con, ruim)
    for ok in ("x" * 500, 'ligar pro "Zé" 😀'):
        assert _criar(con, ok)["texto"] == ok


def test_criar_igual_a_aberta_nao_duplica(con):
    a = _criar(con, "Ligar pro contador", "2026-10-30")
    b = _criar(con, "ligar  pro CONTADOR", "2026-10-30")
    assert b["id"] == a["id"] and b["ja_existia"] is True and a["ja_existia"] is False
    assert con.execute("select count(*) from atividade").fetchone()[0] == 1
    assert _criar(con, "Ligar pro contador", "2026-10-31")["id"] != a["id"]
    atividades.concluir(con, AGORA, "hermes", "hermes", a["id"])
    assert _criar(con, "Ligar pro contador", "2026-10-30")["id"] != a["id"]


def test_listar_ordem_e_status(con):
    con.execute("insert into atividade(texto, vence_em, tem_hora, status, origem, criada_em) values ('vencida','2026-10-26T12:00:00+00:00',1,'aberta','hermes','x')")
    _criar(con, "sem data"); _criar(con, "proxima", "2026-10-30"); _criar(con, "hoje", "2026-10-27")
    assert [i["texto"] for i in atividades.listar(con, AGORA)] == ["vencida", "hoje", "proxima", "sem data"]
    assert [i["prazo"] for i in atividades.listar(con, AGORA)] == ["vencida", "hoje", "proxima", "sem_data"]
    atividades.concluir(con, AGORA, "hermes", "hermes", 2)
    assert [i["texto"] for i in atividades.listar(con, AGORA, "feita")] == ["sem data"]


def test_concluir_e_cancelar_idempotentes_e_exclusivos(con):
    a = _criar(con)
    atividades.concluir(con, AGORA, "hermes", "hermes", a["id"])
    assert atividades.concluir(con, AGORA, "hermes", "hermes", a["id"])["status"] == "feita"
    with pytest.raises(ValueError):
        atividades.cancelar(con, AGORA, "hermes", "hermes", a["id"])
    with pytest.raises(LookupError):
        atividades.concluir(con, AGORA, "hermes", "hermes", 999)
    b = _criar(con, "outra")
    assert atividades.cancelar(con, AGORA, "painel", "painel", b["id"])["status"] == "cancelada"
    assert atividades.cancelar(con, AGORA, "painel", "painel", b["id"])["status"] == "cancelada"


def test_adiar_so_aberta_e_valida_futuro(con):
    a = _criar(con, vence="2026-10-30")
    r = atividades.adiar(con, AGORA, "hermes", "hermes", a["id"], "2026-11-02T09:30")
    assert r["vence_em"] == "2026-11-02T09:30" and r["tem_hora"] is True
    with pytest.raises(ValueError):
        atividades.adiar(con, AGORA, "hermes", "hermes", a["id"], "2026-10-20")
    atividades.concluir(con, AGORA, "hermes", "hermes", a["id"])
    with pytest.raises(ValueError):
        atividades.adiar(con, AGORA, "hermes", "hermes", a["id"], "2026-11-05")


def test_abertas_por_texto_ignora_acento_e_caixa(con):
    _criar(con, "Ligar pro Contador"); _criar(con, "pagar a luz")
    assert [i["texto"] for i in atividades.abertas_por_texto(con, "contadór")] == ["Ligar pro Contador"]


def test_mesmo_texto_em_projetos_diferentes_nao_duplica(con):
    from gabi import projetos
    a = projetos.criar(con, AGORA, "hermes", "hermes", "A")["id"]
    b = projetos.criar(con, AGORA, "hermes", "hermes", "B")["id"]
    x = atividades.criar(con, AGORA, "hermes", "hermes", "ligar", projeto_id=a)
    y = atividades.criar(con, AGORA, "hermes", "hermes", "ligar", projeto_id=b)
    z = atividades.criar(con, AGORA, "hermes", "hermes", "ligar", projeto_id=a)
    assert x["id"] != y["id"] and z["id"] == x["id"] and z["ja_existia"] is True
    assert atividades.criar(con, AGORA, "hermes", "hermes", "ligar")["ja_existia"] is False
