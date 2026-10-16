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


# ---------------- dias_sem_buraco ----------------
def _semanas_uteis(con, ate, semanas=5, pular=()):
    """Movimento em todo dia útil das últimas `semanas` semanas até `ate` (inclusive), menos os dias em `pular`."""
    i = 100
    d = ate - dt.timedelta(days=semanas * 7)
    while d <= ate:
        if d.weekday() < 5 and d not in pular:
            _lanc(con, i, d.isoformat(), -1000 - i)
            i += 1
        d += dt.timedelta(days=1)


def test_dois_dias_uteis_seguidos_sem_movimento_numa_conta_que_sempre_tem_reprova(con):
    _semanas_uteis(con, HOJE, semanas=8, pular={dt.date(2026, 10, 5), dt.date(2026, 10, 6)})  # segunda e terça vazias
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"]
    assert r.ok is False and "2026-10-05" in r.detalhe and "2026-10-06" in r.detalhe


def test_fim_de_semana_sem_movimento_nao_e_buraco(con):
    _semanas_uteis(con, HOJE)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"].ok is True


def test_conta_de_pouco_movimento_nao_reprova(con):
    _lanc(con, 1, "2026-09-02", -100)
    _lanc(con, 2, "2026-09-30", -100)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"].ok is True


def test_historico_curto_nao_reprova(con):
    _lanc(con, 1, "2026-10-07", -100)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"]
    assert r.ok is True and "sem base" in r.detalhe


# ---------------- volume_proximo ----------------
def _volume(con, por_dia: dict):
    i = 500
    for dia, n in por_dia.items():
        for _ in range(n):
            _lanc(con, i, dia, -100)
            i += 1


def test_volume_muito_abaixo_da_mediana_reprova(con):
    base = {(HOJE - dt.timedelta(days=k)).isoformat(): 10 for k in range(2, 16)}
    _volume(con, {**base, "2026-10-07": 2})
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["volume_proximo"]
    assert r.ok is False and "2" in r.detalhe


def test_volume_normal_passa(con):
    base = {(HOJE - dt.timedelta(days=k)).isoformat(): 10 for k in range(2, 16)}
    _volume(con, {**base, "2026-10-07": 6})
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["volume_proximo"].ok is True


def test_mediana_baixa_nao_reprova(con):
    base = {(HOJE - dt.timedelta(days=k)).isoformat(): 1 for k in range(2, 16)}
    _volume(con, base)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["volume_proximo"].ok is True


# ---------------- persistência e rodada conferida ----------------
def test_conferir_grava_as_tres_conferencias(con):
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    tipos = sorted(r["tipo"] for r in con.execute("select tipo from conferencia where rodada_id=?", (rid,)))
    assert tipos == ["dias_sem_buraco", "saldo_final", "volume_proximo"]
    assert isinstance(conferir(con, rid, 1, HOJE)[0], Conferencia)


def test_marcar_conferida_so_se_tudo_ok(con):
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    assert marcar_conferida(con, rid) is True
    assert con.execute("select conferida from rodada where id=?", (rid,)).fetchone()[0] == 1


def test_uma_conferencia_reprovada_impede_a_rodada_conferida(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _saldo(con, "2026-10-08T15:00:00", 1)
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    assert marcar_conferida(con, rid) is False
    assert con.execute("select conferida from rodada where id=?", (rid,)).fetchone()[0] == 0


def test_cartao_nao_confere_buraco_de_dias(con):
    """Cartão gasta de forma irregular: dia útil sem compra não é falha de captura."""
    _semanas_uteis(con, HOJE, pular={dt.date(2026, 10, 6)})
    con.execute("update lancamento set conta_id=2")  # os mesmos lançamentos, agora no cartão (conta 2)
    r = _por_tipo(conferir(con, _rodada(con), 2, HOJE))["dias_sem_buraco"]
    assert r.ok is True and "cartão" in r.detalhe


def _banco_divergente(con, estado):
    """Conta BANK com saldo que não bate com os lançamentos (reprova saldo_final)."""
    con.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b2','XP','BANK',?)", (estado,))
    _saldo(con, "2026-10-07T23:00:00", 100000, conta=3)
    _saldo(con, "2026-10-08T15:00:00", 1, conta=3)


def test_conta_nao_liberada_reprovada_nao_impede_a_rodada_conferida(con):
    _banco_divergente(con, "a_decidir")
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    conferir(con, rid, 3, HOJE)
    assert con.execute("select ok from conferencia where rodada_id=? and conta_id=3 and tipo='saldo_final'", (rid,)).fetchone()[0] == 0  # segue registrada
    assert marcar_conferida(con, rid) is True


def test_conta_liberada_reprovada_impede_a_rodada_conferida(con):
    _banco_divergente(con, "sim")
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    conferir(con, rid, 3, HOJE)
    assert marcar_conferida(con, rid) is False


def test_so_conferencias_de_contas_nao_liberadas_nao_conferem_nada(con):
    con.execute("update conta set estado='a_decidir'")
    rid = _rodada(con)
    conferir(con, rid, 1, HOJE)
    assert marcar_conferida(con, rid) is False  # nenhuma conta que importa foi conferida


def test_rodada_com_erro_ou_aviso_nunca_e_conferida_mesmo_com_conferencias_ok(con):
    r1 = _rodada(con, status="erro")
    r2 = _rodada(con, aviso="falhas: b1")
    for rid in (r1, r2):
        assert all(c.ok for c in conferir(con, rid, 1, HOJE))  # todas aprovadas...
        assert marcar_conferida(con, rid) is False             # ...e ainda assim a rodada incompleta não vale
        assert con.execute("select conferida from rodada where id=?", (rid,)).fetchone()[0] == 0


def test_rodada_sem_nenhuma_conferencia_nao_e_conferida(con):
    assert marcar_conferida(con, _rodada(con)) is False


# ---------------- envelope ----------------
AGORA = dt.datetime(2026, 10, 8, 14, 0, tzinfo=dt.timezone.utc)


def _conferida(con, fonte, fim):
    rid = _rodada(con, fonte=fonte, fim=fim)
    con.execute("update rodada set conferida=1 where id=?", (rid,))
    return rid


def _esperadas(con, fim="2026-10-08T13:00:00+00:00"):
    """Fontes esperadas (notas-nibo, comprovantes) com rodada ok recente: sem elas o envelope as lista como nao_conferida (por desenho)."""
    for f in ("notas-nibo", "comprovantes-paperless"):
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
    _rodada(con, fonte="comprovantes-paperless", fim="2026-10-08T13:00:00+00:00")
    e = envelope(con, {}, agora=AGORA)
    assert e["desatualizado"] is True and e["dados_ate"] == "2026-10-03T12:00:00Z"  # a mais velha manda
    est = {f["nome"]: f["estado"] for f in e["fontes"]}
    assert est == {"open-finance": "ok", "notas-nibo": "parada", "comprovantes-paperless": "ok"}


def test_envelope_sem_nenhuma_rodada_conferida_e_desatualizado(con):
    e = envelope(con, {"a": 1}, agora=AGORA)
    assert e["dados_ate"] is None and e["desatualizado"] is True and e["dados"] == {"a": 1}
    assert {f["nome"] for f in e["fontes"]} == {"notas-nibo", "comprovantes-paperless"}  # só as esperadas, sem rodada


def test_envelope_ignora_backup_e_importacao(con):
    _conferida(con, "backup", "2026-10-08T12:00:00+00:00")
    _conferida(con, "importacao-staging", "2026-10-08T12:00:00+00:00")
    assert {f["nome"] for f in envelope(con, {}, agora=AGORA)["fontes"]} == {"notas-nibo", "comprovantes-paperless"}  # backup/staging ficam de fora


def test_envelope_exatamente_3_dias_ainda_e_atual(con):
    _esperadas(con)
    _conferida(con, "open-finance", "2026-10-05T14:00:00+00:00")
    assert envelope(con, {}, agora=AGORA)["desatualizado"] is False


# ---- calibração com dado real (D1, 09/10/2026) ----
def test_um_dia_util_isolado_sem_movimento_nao_reprova(con):
    _semanas_uteis(con, HOJE, semanas=8, pular={dt.date(2026, 10, 6)})  # só a terça vazia
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"]
    assert r.ok is True and "2026-10-06" in r.detalhe  # passa, mas o detalhe registra o dia


def test_dois_dias_uteis_nao_seguidos_sem_movimento_nao_reprovam(con):
    _semanas_uteis(con, HOJE, semanas=8, pular={dt.date(2026, 10, 2), dt.date(2026, 10, 6)})  # sexta e terça (segunda tem movimento)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"].ok is True


def test_cartao_nao_confere_volume(con):
    _volume(con, {"2026-10-07": 0, **{f"2026-09-{d}": 4 for d in (24, 25, 28, 29, 30)}, "2026-10-01": 4, "2026-10-02": 4, "2026-10-05": 4, "2026-10-06": 4})
    r = _por_tipo(conferir(con, _rodada(con), 2, HOJE))["volume_proximo"]
    assert r.ok is True and "cartão" in r.detalhe


def _fatura(con, total, status="PAST_DUE_UNCONFIRMED", vencimento="2026-10-05"):
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, conta_id, pagamento_status) values (?,?,?,?,2,?)",
                (f"f{total}", "c1", vencimento, total, status))


def _saldo_caiu(con, valor):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _saldo(con, "2026-10-08T15:00:00", 100000 - valor)  # sem nenhum lançamento postado


def test_saldo_final_explicado_por_fatura_pendente_passa_com_detalhe(con):
    _fatura(con, 40166)
    _saldo_caiu(con, 40166)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True and "fatura" in r.detalhe


def test_saldo_final_sem_fatura_que_explique_continua_reprovando(con):
    _fatura(con, 12345)
    _saldo_caiu(con, 40166)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"].ok is False


def test_saldo_final_explicado_por_lancamento_pendente_passa_com_detalhe(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _lanc(con, 1, "2026-10-08", -40166, status="pending")  # o banco já abateu o pendente do saldo
    _saldo(con, "2026-10-08T15:00:00", 100000 - 40166)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True and "pendente" in r.detalhe


def test_saldo_final_pendente_de_outro_valor_nao_explica(con):
    _saldo(con, "2026-10-07T23:00:00", 100000)
    _lanc(con, 1, "2026-10-08", -9999, status="pending")
    _saldo(con, "2026-10-08T15:00:00", 100000 - 40166)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"].ok is False


# ---------------- buraco em conta de movimento irregular (ADR-009, revisão 09/10 noite) ----------------
def _conta_irregular(con, vazios):
    """~60% dos dias úteis com movimento (cada dia da semana com movimento em 3 de 5 semanas) fora da janela de 14 dias;
    na janela, todo dia útil tem movimento, menos `vazios`."""
    i, d = 1000, HOJE - dt.timedelta(days=56)
    while d <= HOJE:
        if d.weekday() < 5:
            semana = (d - dt.date(2026, 8, 10)).days // 7
            na_janela = (HOJE - d).days <= 14
            cheio = (not na_janela and d.weekday() not in {semana % 5, (semana + 2) % 5}) or (na_janela and d not in vazios)
            if cheio and d != HOJE:
                _lanc(con, i, d.isoformat(), -1000 - i)
                i += 1
        d += dt.timedelta(days=1)


def test_conta_de_movimento_irregular_tolera_dois_dias_uteis_seguidos_vazios(con):
    _conta_irregular(con, vazios={dt.date(2026, 10, 5), dt.date(2026, 10, 6)})
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"]
    assert r.ok is True and "2026-10-05" in r.detalhe and "irregular" in r.detalhe


def test_conta_de_movimento_irregular_reprova_quatro_dias_uteis_seguidos_vazios(con):
    _conta_irregular(con, vazios={dt.date(2026, 10, 5), dt.date(2026, 10, 6), dt.date(2026, 10, 7)} | {dt.date(2026, 10, 2)})
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["dias_sem_buraco"]
    assert r.ok is False and "2026-10-02" in r.detalhe


def test_saldo_que_ja_traz_lancamentos_do_dia_base_lidos_depois_do_saldo_passa(con):
    # o saldo de 07/10 foi lido às 15h; entrou um crédito de 07/10 à noite; o saldo de 08/10 já o traz (caso real C6, 15/10 -> 16/10)
    _saldo(con, "2026-10-07T15:00:00", 100000)
    _lanc(con, 1, "2026-10-07", 83144)
    _saldo(con, "2026-10-08T15:00:00", 183144)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"]
    assert r.ok is True and "2026-10-07" in r.detalhe


def test_saldo_divergente_que_nao_bate_nem_com_o_dia_base_continua_reprovando(con):
    _saldo(con, "2026-10-07T15:00:00", 100000)
    _lanc(con, 1, "2026-10-07", 83144)
    _saldo(con, "2026-10-08T15:00:00", 190000)  # sobrou 6.856, que nenhum lançamento explica
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["saldo_final"].ok is False


def test_dia_sem_lancamento_e_sem_mudanca_de_saldo_nao_reprova_o_volume(con):
    base = {(HOJE - dt.timedelta(days=k)).isoformat(): 10 for k in range(2, 16)}
    _volume(con, base)  # ontem (07/10): nenhum lançamento
    _saldo(con, "2026-10-06T22:00:00", 50000)
    _saldo(con, "2026-10-07T22:00:00", 50000)
    r = _por_tipo(conferir(con, _rodada(con), 1, HOJE))["volume_proximo"]
    assert r.ok is True and "dia vazio" in r.detalhe


def test_dia_sem_lancamento_mas_saldo_mudou_continua_reprovando_o_volume(con):
    base = {(HOJE - dt.timedelta(days=k)).isoformat(): 10 for k in range(2, 16)}
    _volume(con, base)
    _saldo(con, "2026-10-06T22:00:00", 50000)
    _saldo(con, "2026-10-07T22:00:00", 70000)
    assert _por_tipo(conferir(con, _rodada(con), 1, HOJE))["volume_proximo"].ok is False
