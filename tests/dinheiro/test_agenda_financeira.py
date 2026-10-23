import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.agenda_financeira import montar

BRT = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 10, 16, 7, 5, tzinfo=BRT)  # sexta-feira
MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','Itau','BANK','Itaú','sim')")
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-10-16T06:05:00', 1000000)")  # R$ 10.000,00
    return c


def comp(con, id_, venc, estado, valor, fonte="valores_do_mes", nome=None, forma=""):
    con.execute("insert into compromisso(id, origem, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, estado, forma) values (?,?,?,?,?,?,?,?,?)",
                (id_, "linha", nome or id_, venc, venc, valor, fonte, estado, forma))


def texto(con, **k):
    return "\n".join(montar(con, AGORA, **k))


def test_diaria_mostra_saldo_com_hora_e_proximos_dias_em_ordem(con):
    comp(con, "b", "2026-10-19", "aberto", 186362, nome="Fatura Personnalite")
    comp(con, "a", "2026-10-18", "aberto", 50000, nome="Escola")
    t = texto(con)
    assert t.startswith("💰 *Financeiro*") and "Saldo: R$ 10.000,00" in t
    assert t.index("• 18/10 Escola R$ 500,00") < t.index("• 19/10 Fatura Personnalite R$ 1.863,62")


def test_valor_estimado_vai_com_til_e_debito_automatico_marcado(con):
    comp(con, "e", "2026-10-17", "aberto", 30000, fonte="ultimo", nome="Sem Parar")
    comp(con, "d", "2026-10-18", "aberto", 6400, fonte="padrao", nome="Vivo", forma="debito_automatico")
    t = texto(con)
    assert "• 17/10 Sem Parar ~R$ 300,00" in t and "• 18/10 Vivo ~R$ 64,00 (déb. auto)" in t


def test_dia_vazio_diz_que_nao_ha_nada(con):
    t = texto(con)
    assert "• Hoje: nada" in t and "• Atrasadas: 0" in t and "Nada nos próximos 3 dias" in t


def test_atrasadas_contam_e_somam(con):
    comp(con, "x", "2026-10-10", "atrasado", 120000)
    comp(con, "y", "2026-10-12", "atrasado", 80000)
    assert "• ⚠️ Atrasadas: 2 (R$ 2.000,00)" in texto(con)


def test_o_que_vence_hoje_aparece_em_hoje(con):
    comp(con, "h", "2026-10-16", "aberto", 25000, nome="Condomínio")
    t = texto(con)
    assert "• Hoje: Condomínio R$ 250,00" in t and "Hoje: nada" not in t


def test_falta_de_saldo_avisa_o_dia_e_o_valor(con):
    comp(con, "g", "2026-10-18", "aberto", 1300000, nome="Aluguel")
    t = texto(con)
    assert "⚠️ Falta R$ 3.000,00 em 18/10" in t


def test_sem_falta_mostra_o_saldo_previsto(con):
    comp(con, "g", "2026-10-18", "aberto", 100000)
    t = texto(con)
    assert "Previsão: R$ 9.000,00 em 19/10" in t and "Falta" not in t


def test_valor_a_confirmar_nao_entra_na_soma_e_e_dito(con):
    comp(con, "v", "2026-10-17", "aberto", None, nome="Carla (reembolso)")
    t = texto(con)
    assert "• 17/10 Carla (reembolso) valor a confirmar" in t and "Previsão: R$ 10.000,00" in t


def test_saldo_com_leitura_antiga_avisa(con):
    con.execute("update saldo set em='2026-10-15T20:00:00'")  # 11 h antes
    t = texto(con)
    assert "⚠️ leitura de 15/10 20:00" in t


def test_saldo_recente_nao_avisa_de_leitura(con):
    assert "leitura de" not in texto(con)


def test_lista_longa_corta_em_doze_e_diz_quantos_faltam(con):
    for i in range(15):
        comp(con, f"c{i}", "2026-10-18", "aberto", 1000, nome=f"Conta {i:02d}")
    t = texto(con)
    assert t.count("• 18/10 Conta") == 12 and "+3 outros" in t


def test_avisa_que_entradas_alem_das_notas_nao_contam(con):
    assert "entradas" in texto(con).lower().splitlines()[-1]


def test_semanal_agrupa_por_semana_e_aponta_o_primeiro_aperto(con):
    comp(con, "s1", "2026-10-20", "aberto", 400000, nome="A")
    comp(con, "s2", "2026-10-27", "aberto", 900000, nome="B")
    t = texto(con, dias=30, semanal=True)
    assert t.startswith("💰 *Financeiro: próximos 30 dias*")
    assert "• 19/10–25/10: sai R$ 4.000,00" in t and "• 26/10–01/11: sai R$ 9.000,00" in t
    assert "⚠️ Primeiro aperto: 27/10 (falta R$ 3.000,00)" in t


def test_semanal_sem_aperto(con):
    comp(con, "s1", "2026-10-20", "aberto", 100000)
    assert "Sem falta de caixa no período" in texto(con, dias=30, semanal=True)


def conta_bank(con, apelido, saldo, estado="sim"):
    n = con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values (?,?,?,?,?)",
                    (apelido, apelido, "BANK", apelido, estado)).lastrowid
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (?, '2026-10-16T06:05:00', ?)", (n, saldo))


def test_conta_negativa_vira_aviso_mesmo_com_caixa_total_positivo(con):
    conta_bank(con, "Santander", -73707)
    t = texto(con)
    assert "⚠️ Saldo negativo: Santander -R$ 737,07" in t
    assert "Saldo: R$ 9.262,93" in t  # o total continua o do caixa único


def test_conta_negativa_diz_onde_ha_saldo_para_cobrir(con):
    conta_bank(con, "Santander", -73707)
    assert "Por banco: Itaú R$ 10.000,00 · ⚠️ Santander -R$ 737,07" in texto(con)


def test_varias_contas_negativas_somam_e_listam_a_mais_funda_primeiro(con):
    conta_bank(con, "Santander", -73707)
    conta_bank(con, "XP", -200000)
    t = texto(con)
    assert t.index("XP -R$ 2.000,00") < t.index("Santander -R$ 737,07")


def test_sem_conta_negativa_nao_avisa(con):
    conta_bank(con, "C6", 5000)
    assert "Saldo negativo" not in texto(con)


def test_conta_nao_liberada_nao_entra_no_aviso(con):
    conta_bank(con, "Velha", -999900, estado="nao")
    assert "Saldo negativo" not in texto(con)


def test_semanal_tambem_avisa_conta_negativa(con):
    conta_bank(con, "Santander", -73707)
    assert "⚠️ Saldo negativo: Santander -R$ 737,07" in texto(con, dias=30, semanal=True)


def serie(con, desc, valores, prefixo="s"):
    """Um lançamento por mês de 2026-05 a 2026-10 (o último valor é o do mês corrente)."""
    meses = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"][-len(valores):]
    for m, v in zip(meses, valores):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                    "values (1,?,?,?,?,'caixa+custo','posted')", (f"{prefixo}{m}", f"{m}-05", v, desc))


def test_diaria_traz_fora_do_normal(con):
    serie(con, "ENERGIA ELETRICA", [-30000, -31000, -29000, -30500, -29500, -90000])
    t = texto(con)
    assert "Fora do normal: ENERGIA ELETRICA R$ 900,00 (normal ~R$ 300,00)" in t


def test_diaria_sem_historico_nao_ganha_linha(con):
    assert "Fora do normal" not in texto(con)


def test_diaria_limita_a_tres_avisos(con):
    for n in "ABCD":
        serie(con, f"CONTA {n}", [-30000, -31000, -29000, -30500, -29500, -90000], prefixo=n)
    t = texto(con)
    assert t.count("Fora do normal:") == 3 and "+1 fora do normal" in t


def _lanc(con, conta, ext, data, valor, desc):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                "values (?,?,?,?,?,'caixa+custo','posted')", (conta, ext, data, valor, desc))


def test_desvio_ignora_conta_nao_liberada(con):
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b9','X','BANK','Terceiro','nao')")
    for m, v in zip(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"], [-30000, -31000, -29000, -30500, -29500, -90000]):
        _lanc(con, 2, f"z{m}", f"{m}-05", v, "ENERGIA")
    assert "Fora do normal" not in texto(con)


def test_desvio_nao_compara_o_reembolso_com_a_pensao(con):
    for m in ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]:
        _lanc(con, 1, f"p{m}", f"{m}-20", -300000, "PIX MARIA")
        _lanc(con, 1, f"r{m}", f"{m}-03", -50000, "PIX MARIA")
    _lanc(con, 1, "r10", "2026-10-03", -50000, "PIX MARIA")  # outubro: só o reembolso saiu até dia 16
    assert "Fora do normal" not in texto(con)


def test_falha_no_desvio_nao_derruba_a_diaria(con, monkeypatch):
    def estoura(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr("gabi.dinheiro.agenda_financeira.fora_do_normal", estoura)
    t = texto(con)
    assert t.startswith("💰 *Financeiro*") and "Fora do normal" not in t


def test_semanal_traz_cenario_com_recorrentes_esperadas(con):
    for i, m in enumerate(["2026-06", "2026-07", "2026-08", "2026-09"]):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                    "values (1,?,?,2000000,'PIX RECEBIDO CLIENTE FIXO','caixa+custo','posted')", (f"r{i}", f"{m}-20"))
    t = texto(con, dias=30, semanal=True)
    assert "Com recorrentes esperadas (médias, +R$ 20.000,00 em entradas)" in t


def test_semanal_sem_recorrentes_nao_ganha_o_segundo_cenario(con):
    assert "Com recorrentes esperadas" not in texto(con, dias=30, semanal=True)


def test_saldo_por_banco_aparece_separado_mesmo_sem_conta_negativa(con):
    conta_bank(con, "Bradesco", 18875)
    t = texto(con)
    assert "Por banco: Itaú R$ 10.000,00 · Bradesco R$ 188,75" in t and "⚠️" not in t.split("Por banco:")[1].splitlines()[0]
    assert "Saldo negativo" not in t


def test_saldo_por_banco_tambem_na_semanal(con):
    conta_bank(con, "Santander", -73707)
    assert "Por banco: Itaú R$ 10.000,00 · ⚠️ Santander -R$ 737,07" in texto(con, dias=30, semanal=True)
