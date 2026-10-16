from tests.dinheiro.test_esperados import HOJE, con, cred, mensal  # noqa: F401  (fixture e auxiliares do "a receber")

from gabi.dinheiro.cobranca_atraso import rascunhos


def test_entrada_atrasada_vira_rascunho_sem_enviar_nada(con):
    mensal(con, [5, 6, 7, 8, 9], 7, 10208.0)
    [r] = rascunhos(con, HOJE)
    assert "R$ 10.208,00" in r["rascunho"] and f"dia {r['dia_limite']}" in r["rascunho"]
    assert "nada foi enviado" in r["aviso"].lower() and set(r) == {"pagador", "valor", "dia_limite", "dias_atraso", "confianca", "rascunho", "aviso"}


def test_quem_ja_pagou_este_mes_nao_gera_rascunho(con):
    mensal(con, [5, 6, 7, 8, 9, 10], 7, 10208.0)
    assert rascunhos(con, HOJE) == []


def test_filtro_por_pagador_ignora_caixa_e_exclui_os_outros(con):
    mensal(con, [5, 6, 7, 8, 9], 7, 10208.0)
    assert len(rascunhos(con, HOJE, "cliente x")) == 1 and rascunhos(con, HOJE, "outro nome") == []


def test_contrato_novo_pede_confirmar_o_pagador(con):
    cred(con, "2026-08-10", 10208.0, "X2 INTERMEDIACOES LTDA")
    cred(con, "2026-09-14", 10208.0, "X2 INTERMEDIACOES LTDA")
    [r] = rascunhos(con, HOJE)
    assert r["confianca"] == "nova" and "confirme que o pagador é este" in r["aviso"]
