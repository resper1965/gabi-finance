import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.conferencia import Conferencia, conferir, marcar_conferida
from gabi.envelope import envelope

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 8)  # quinta-feira


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','C6','BANK','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','CREDIT','sim')")
    return c


def _rodada(con, fonte="open-finance", status="ok", fim="2026-10-08T12:00:00+00:00", aviso=None):
    return con.execute("insert into rodada(fonte, inicio, fim, status, erro) values (?,?,?,?,?)", (fonte, fim, fim, status, aviso)).lastrowid


def _lanc(con, i, data, valor, status="posted", conta=1):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, status) values (?,?,?,?,?)", (conta, f"l{i}", data, valor, status))


def _saldo(con, em, centavos, conta=1):
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (?,?,?)", (conta, em, centavos))


def _por_tipo(lista):
    return {c.tipo: c for c in lista}


# ---------------- saldo_final ----------------
def test_saldo_que_bate_com_os_lancamentos_passa(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _lanc(con, 1, "2026-10-08", -3000)
    _lanc(con, 2, "2026-10-08", 5000)
    _saldo(con, "2026-10-08T15:00:00", 102000)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True


def test_saldo_divergente_reprova_e_diz_a_diferenca(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _lanc(con, 1, "2026-10-08", -3000)
    _saldo(con, "2026-10-08T15:00:00", 95000)  # caiu 50,00 mas só há -30,00 de lançamentos
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is False and "2000" in r.detalhe  # faltam 20,00 (2000 centavos) de lançamentos


def test_pending_nao_entra_na_conta_do_saldo(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _lanc(con, 1, "2026-10-08", -3000)
    _lanc(con, 2, "2026-10-08", -999, status="pending")
    _saldo(con, "2026-10-08T15:00:00", 97000)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"].ok is True


def test_sem_dois_dias_de_saldo_nao_ha_base_e_nao_reprova(con):
    _saldo(con, "2026-10-08T15:00:00", 97000)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True and "sem base" in r.detalhe


def test_cartao_nao_confere_saldo(con):
    _saldo(con, "2026-10-07T23:00:00", -50000, conta=2)
    _saldo(con, "2026-10-08T15:00:00", -90000, conta=2)
    r = _por_tipo(conferir(con, _rodada(con), 2, HOJE))["saldo_final"]
    assert r.ok is True and "cartão" in r.detalhe


# ---------------- persistência e rodada conferida (ADR-023: a conferência informa, não trava) ----------------
def test_conferir_grava_so_o_saldo_final(con):
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    assert [r["tipo"] for r in con.execute("select tipo from conferencia where rodada_id=?", (rid,))] == ["saldo_final"]
    assert isinstance(conferir(con, rid, 1, HOJE)[0], Conferencia)
    assert con.execute("select count(*) from conferencia where rodada_id=?", (rid,)).fetchone()[0] == 1  # reconferir substitui


def test_rodada_ok_e_conferida_mesmo_com_divergencia(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _saldo(con, "2026-10-08T15:00:00", 1)
    rid = _rodada(con)
    assert conferir(con, rid, 1, HOJE)[0].ok is False
    assert marcar_conferida(con, rid) is True
    assert con.execute("select conferida from rodada where id=?", (rid,)).fetchone()[0] == 1


def test_rodada_ok_sem_nenhuma_conferencia_e_conferida(con):
    assert marcar_conferida(con, _rodada(con)) is True


def test_rodada_com_erro_ou_aviso_nunca_e_conferida(con):
    for rid in (_rodada(con, status="erro"), _rodada(con, aviso="falhas: b1")):
        conferir(con, rid, 1, HOJE)
        assert marcar_conferida(con, rid) is False
        assert con.execute("select conferida from rodada where id=?", (rid,)).fetchone()[0] == 0


def test_pendentes_nao_explicam_mais_a_diferenca(con):
    _saldo(con, "2026-10-07T23:00:00", 124017)
    for i, v in enumerate((-87714, -33043)):
        _lanc(con, i + 1, "2026-10-08", v, status="pending")
    _saldo(con, "2026-10-08T15:00:00", 124017 - 120757)
    r = conferir(con, _rodada(con), 1, HOJE)[0]
    assert r.ok is False and "-120757" in r.detalhe  # só informa: a rodada segue conferida


# ---------------- envelope ----------------
AGORA = dt.datetime(2026, 10, 8, 14, 0, tzinfo=dt.timezone.utc)


def _conferida(con, fonte, fim):
    rid = _rodada(con, fonte=fonte, fim=fim)
    con.execute("update rodada set conferida=1 where id=?", (rid,))
    return rid


def _esperadas(con, fim="2026-10-08T13:00:00+00:00"):
    """Fontes esperadas (notas-nibo, comprovantes) com rodada ok recente: sem elas o envelope as lista como nao_conferida (por desenho)."""
    for f in ("notas-nibo",):
        _rodada(con, fonte=f, fim=fim)


def test_envelope_usa_a_rodada_conferida_nao_a_ultima_tentativa(con):
    _esperadas(con)
    _conferida(con, "open-finance", "2026-10-08T12:00:00+00:00")
    _rodada(con, fonte="open-finance", status="erro", fim="2026-10-08T13:00:00+00:00")
    e = envelope(con, {"x": 1}, agora=AGORA)
    assert e["dados_ate"] == "2026-10-08T12:00:00Z" and e["desatualizado"] is False and e["dados"] == {"x": 1}
    assert [f for f in e["fontes"] if f["nome"] == "open-finance"] == [{"nome": "open-finance", "estado": "erro", "ultima": "2026-10-08T12:00:00Z"}]


def test_envelope_tentativa_ok_mas_nao_conferida_aparece_como_nao_conferida(con):
    _esperadas(con)
    _conferida(con, "open-finance", "2026-10-08T10:00:00+00:00")
    _rodada(con, fonte="open-finance", status="ok", fim="2026-10-08T13:00:00+00:00")
    e = envelope(con, {}, agora=AGORA)
    assert e["fontes"][-1]["estado"] == "nao_conferida" and e["dados_ate"] == "2026-10-08T10:00:00Z"


def test_envelope_desatualizado_apos_3_dias_aponta_a_fonte_parada(con):
    _conferida(con, "open-finance", "2026-10-08T12:00:00+00:00")
    _conferida(con, "notas-nibo", "2026-10-03T12:00:00+00:00")
    e = envelope(con, {}, agora=AGORA)
    assert e["desatualizado"] is True and e["dados_ate"] == "2026-10-03T12:00:00Z"  # a mais velha manda
    est = {f["nome"]: f["estado"] for f in e["fontes"]}
    assert est == {"open-finance": "ok", "notas-nibo": "parada"}


def test_envelope_sem_nenhuma_rodada_conferida_e_desatualizado(con):
    e = envelope(con, {"a": 1}, agora=AGORA)
    assert e["dados_ate"] is None and e["desatualizado"] is True and e["dados"] == {"a": 1}
    assert {f["nome"] for f in e["fontes"]} == {"notas-nibo"}  # só as esperadas, sem rodada


def test_envelope_ignora_backup_e_importacao(con):
    _conferida(con, "backup", "2026-10-08T12:00:00+00:00")
    _conferida(con, "importacao-staging", "2026-10-08T12:00:00+00:00")
    assert {f["nome"] for f in envelope(con, {}, agora=AGORA)["fontes"]} == {"notas-nibo"}  # backup/staging ficam de fora


def test_envelope_exatamente_3_dias_ainda_e_atual(con):
    _esperadas(con)
    _conferida(con, "open-finance", "2026-10-05T14:00:00+00:00")
    assert envelope(con, {}, agora=AGORA)["desatualizado"] is False


def test_saldo_final_diferenca_de_1_centavo_e_arredondamento(con):
    # Bradesco 21/10/2026: rendimento do investimento automático moveu o saldo em 1 centavo sem lançamento
    _saldo(con, "2026-10-07T23:00:00", 18875)
    _saldo(con, "2026-10-08T15:00:00", 18876)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True and "arredondamento" in r.detalhe


def test_saldo_final_diferenca_de_2_centavos_ainda_reprova(con):
    _saldo(con, "2026-10-07T23:00:00", 18875)
    _saldo(con, "2026-10-08T15:00:00", 18877)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"].ok is False
