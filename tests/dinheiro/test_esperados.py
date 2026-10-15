import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.agenda_financeira import montar
from gabi.dinheiro.esperados import entradas_esperadas

MIGR = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 20)
_n = iter(range(1, 100000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','C6','BANK','sim')")        # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('cc1','Itau','CREDIT','sim')")    # 2
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b2','Outro','BANK','a_decidir')")  # 3
    return c


def cred(con, data, valor_reais, desc="Pix recebido de CLIENTE X LTDA", conta=1):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza) values (?,?,?,?,?, 'caixa')",
                (conta, f"t{next(_n)}", data, int(valor_reais * 100), desc))


def mensal(con, meses, dia, valor, desc="Pix recebido de CLIENTE X LTDA", conta=1):
    for m in meses:
        cred(con, f"2026-{m:02d}-{dia:02d}", valor, desc, conta)


def _por_nome(r, trecho):
    return [e for e in r if trecho in e["pagador"].upper()]


def test_pagador_regular_que_nao_veio_este_mes_e_passou_do_dia_costumeiro_esta_atrasado(con):
    mensal(con, [5, 6, 7, 8, 9], 7, 10208.0)
    [e] = entradas_esperadas(con, HOJE)
    assert e["atrasada"] and e["valor_centavos"] == 1020800 and e["dia_limite"] <= 9 and e["confianca"] == "alta"


def test_se_ja_veio_este_mes_nao_esta_atrasado(con):
    mensal(con, [5, 6, 7, 8, 9, 10], 7, 10208.0)
    [e] = entradas_esperadas(con, HOJE)
    assert not e["atrasada"]


def test_antes_do_dia_costumeiro_nao_esta_atrasado(con):
    mensal(con, [5, 6, 7, 8, 9], 26, 9204.69)
    [e] = entradas_esperadas(con, HOJE)  # dia 20: ainda no prazo
    assert not e["atrasada"] and e["dia_limite"] >= 26


def test_contrato_novo_com_dois_meses_seguidos_entra_como_nova(con):
    cred(con, "2026-08-10", 10208.0, "X2 INTERMEDIACOES LTDA")
    cred(con, "2026-09-14", 10208.0, "X2 INTERMEDIACOES LTDA")
    [e] = entradas_esperadas(con, HOJE)
    assert e["confianca"] == "nova" and e["atrasada"] and "X2" in e["pagador"].upper()


def test_um_so_pagamento_nao_cria_expectativa(con):
    cred(con, "2026-09-14", 10208.0, "X2 INTERMEDIACOES LTDA")
    assert entradas_esperadas(con, HOJE) == []


def test_camadas_do_mesmo_pagador_viram_series_separadas(con):
    mensal(con, [5, 6, 7, 8, 9], 5, 16000.0, "72027097000137-NESS PROCESSOS E TECNOLOG")
    mensal(con, [5, 6, 7, 8, 9], 25, 26258.0, "72027097000137-NESS PROCESSOS E TECNOLOG")
    r = entradas_esperadas(con, HOJE)
    assert sorted(e["valor_centavos"] for e in r) == [1600000, 2625800]
    camada_25 = next(e for e in r if e["valor_centavos"] == 2625800)
    assert not camada_25["atrasada"]            # dia 25 ainda não chegou
    assert next(e for e in r if e["valor_centavos"] == 1600000)["atrasada"]


def test_valor_proximo_este_mes_conta_como_ocorrido_mesmo_com_variacao(con):
    mensal(con, [5, 6, 7, 8, 9], 7, 20000.0)
    cred(con, "2026-10-09", 19400.0)             # 3% abaixo: é o mesmo pagamento
    assert not entradas_esperadas(con, HOJE)[0]["atrasada"]


def test_ignora_resgate_rendimento_valor_pequeno_cartao_e_conta_nao_liberada(con):
    mensal(con, [5, 6, 7, 8, 9], 7, 8967.0, "RESGATE DE CDB")
    mensal(con, [5, 6, 7, 8, 9], 7, 300.0, "Pix recebido de LOJA")
    mensal(con, [5, 6, 7, 8, 9], 7, 5000.0, "Pix recebido de CARTAO", conta=2)
    mensal(con, [5, 6, 7, 8, 9], 7, 5000.0, "Pix recebido de NAO LIBERADA", conta=3)
    assert entradas_esperadas(con, HOJE) == []


def test_pagador_que_parou_ha_meses_nao_gera_alerta(con):
    mensal(con, [3, 4, 5, 6], 7, 4000.0)         # último pagamento em junho
    assert [e for e in entradas_esperadas(con, HOJE) if e["atrasada"]] == []


def test_agenda_financeira_traz_o_a_receber_atrasado(con):
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-10-20T06:05:00', 1000000)")
    mensal(con, [5, 6, 7, 8, 9], 7, 10208.0, "Pix recebido de MATHEUS CONTRATO LTDA")
    t = "\n".join(montar(con, dt.datetime(2026, 10, 20, 7, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))))
    assert "• ⚠️ A receber atrasado: Matheus Contrato Ltda ~R$ 10.208,00 (costuma cair até o dia" in t


def test_agenda_financeira_sem_atraso_nao_menciona_a_receber(con):
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-10-20T06:05:00', 1000000)")
    assert "A receber" not in "\n".join(montar(con, dt.datetime(2026, 10, 20, 7, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))))
