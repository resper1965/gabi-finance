"""conciliar em centavos: 4 estados, casamento por vencimento (um teste por regra)."""
import datetime as dt

from gabi.dinheiro.conciliacao import conciliar

HOJE = dt.date(2026, 10, 8)
AGORA = dt.datetime.fromisoformat("2026-10-08T15:00:00-03:00")
P = {"janela_antes_dias": 10, "tolerancia_fixo": 0.01, "tolerancia_valor": 1.0, "horas_conta_parada": 24}
ESTADO = {"c1": {"tipo": "BANK", "pj": 0, "banco": "C6 Bank", "nome": "Conta C6",
                 "ult_sync_ok": "2026-10-08T14:00:00-03:00", "ult_tx_real": "2026-10-07"}}
ESTADOS = {"pago", "aberto", "atrasado", "a_conferir"}


def _comp(id, venc, valor_centavos=None, valor_tipo="fixo", valor_fonte="padrao", forma="pix", chaves=("FAVORECIDO",),
          linha_id=None, **kw):
    c = {"id": id, "origem": "planilha", "linha_id": linha_id, "nome": id, "vencimento": venc, "vencimento_util": venc,
         "valor_centavos": valor_centavos, "valor_fonte": valor_fonte if valor_centavos is not None else None,
         "valor_tipo": valor_tipo, "forma": forma, "account_id": None, "extrato_chaves": list(chaves),
         "cartao_account_id": None, "linha": None, "payment_status": None}
    c.update(kw)
    return c


def _tx(id, data, valor_centavos, descricao, account_id="c1", tipo_conta="BANK", **kw):
    return {"id": id, "account_id": account_id, "tipo_conta": tipo_conta, "data": data, "descricao": descricao,
            "valor_centavos": valor_centavos, "categoria": None, "natureza": "caixa+custo", **kw}


def _rodar(comps, txs, vinculos=None, estado=None, pagos=(), hoje=HOJE, agora=AGORA):
    return conciliar(comps, txs, vinculos or {}, estado or ESTADO, list(pagos), P, hoje, agora)


def _fatura(id="cartao:2026-10", venc="2026-10-05", valor=80000, **kw):
    return _comp(id, venc, valor, valor_tipo="variavel", valor_fonte="fatura", forma="fatura", chaves=("FATURA 9999",),
                 linha={"cartao": "Cartao Itau"}, **kw)


# ---------- vínculo gravado ----------
def test_vinculo_gravado_paga_e_tira_o_lancamento_do_jogo():
    a, b = _comp("a:2026-10", "2026-10-05", 200000), _comp("b:2026-10", "2026-10-05", 200000)
    res, novos = _rodar([a, b], [_tx("t1", "2026-10-05", -200000, "PIX FAVORECIDO")], {"t1": "a:2026-10"})
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["metodo"], res["a:2026-10"]["tx_id"]) == ("pago", "favorecido", "t1")
    assert res["b:2026-10"]["estado"] == "atrasado"
    assert novos == []


def test_vinculo_de_outra_rodada_nao_paga_outro():
    a = _comp("a:2026-10", "2026-10-05", 200000)
    res, novos = _rodar([a], [_tx("t1", "2026-10-05", -200000, "PIX FAVORECIDO")], {"t1": "x:2026-09"})
    assert res["a:2026-10"]["tx_id"] != "t1" and res["a:2026-10"]["estado"] == "atrasado"
    assert novos == []


# ---------- candidatos ----------
def test_transferencia_propria_e_conta_pj_ficam_fora():
    estado = {**ESTADO, "pj1": {**ESTADO["c1"], "pj": 1}}
    txs = [_tx("t1", "2026-10-05", -200000, "PIX FAVORECIDO", natureza="neutro"),
           _tx("t2", "2026-10-05", -200000, "PIX FAVORECIDO", account_id="pj1")]
    res, _ = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], txs, estado=estado)
    assert res["a:2026-10"]["estado"] == "atrasado"


# ---------- por favorecido ----------
def test_favorecido_na_janela_paga():
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-09-25", -200000, "PIX FAVORECIDO")])
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["metodo"], res["a:2026-10"]["pago_em"]) == ("pago", "favorecido", "2026-09-25")
    assert novos == [("t1", "a:2026-10", "favorecido", 0)]


def test_favorecido_fora_da_janela_nao_paga():
    res, _ = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-09-24", -200000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["estado"] == "atrasado"


def test_pix_atrasado_fica_com_o_mes_vencido():
    """O Pix de 28/10 está na janela dos dois e mais perto de nov; a ordem por vencimento dá a out."""
    out, nov = _comp("a:2026-10", "2026-10-05", 200000, linha_id="a"), _comp("a:2026-11", "2026-11-05", 200000, linha_id="a")
    estado = {"c1": {**ESTADO["c1"], "ult_sync_ok": "2026-10-30T14:00:00-03:00"}}
    res, _ = _rodar([nov, out], [_tx("t1", "2026-10-28", -200000, "PIX FAVORECIDO")], estado=estado,
                    hoje=dt.date(2026, 10, 30), agora=dt.datetime.fromisoformat("2026-10-30T15:00:00-03:00"))
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["tx_id"]) == ("pago", "t1")
    assert res["a:2026-11"]["estado"] == "aberto"


def test_mais_proximo_do_vencimento_ganha():
    a = _comp("a:2026-10", "2026-10-05", 200000)
    res, _ = _rodar([a], [_tx("t2", "2026-10-01", -200000, "PIX FAVORECIDO"), _tx("t1", "2026-10-04", -200000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["tx_id"] == "t1"
    res, _ = _rodar([a], [_tx("t4", "2026-10-06", -200000, "PIX FAVORECIDO"), _tx("t3", "2026-10-04", -200000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["tx_id"] == "t3"  # empate de distância: id menor


def test_valor_que_encaixa_ganha_da_data_mais_proxima():
    txs = [_tx("t1", "2026-10-05", -5000, "PIX FAVORECIDO"), _tx("t2", "2026-10-01", -200000, "PIX FAVORECIDO")]
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], txs)
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["tx_id"]) == ("pago", "t2")
    assert novos == [("t2", "a:2026-10", "favorecido", 0)]


def test_baixa_manual_com_valor_da_a_diferenca_em_centavos():
    res, novos = _rodar([_iptu()], [], pagos=[{**_BAIXA, "valor_centavos": 49000}])
    assert res["iptu:2026-10"]["diferenca_centavos"] == -1000 and novos[0][3] == -1000


# ---------- por valor ----------
def test_por_valor_paga_quando_ninguem_tem_a_chave():
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 200000, chaves=("ALUGUEL",))],
                        [_tx("t1", "2026-10-05", -200050, "BOLETO 123456")])
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["metodo"]) == ("pago", "valor")
    assert novos == [("t1", "a:2026-10", "valor", 50)]


def test_por_valor_so_sem_favorecido_de_ninguem():
    a = _comp("a:2026-10", "2026-10-05", 200000, chaves=("ALUGUEL",))
    b = _comp("b:2026-11", "2026-11-20", 999, chaves=("OUTRO",))
    res, _ = _rodar([a, b], [_tx("t1", "2026-10-05", -200000, "PIX OUTRO")])
    assert res["a:2026-10"]["estado"] == "atrasado"


def test_pagamento_de_fatura_so_paga_fatura():
    a = _comp("escola:2026-10", "2026-10-05", 74210, forma="boleto", chaves=("ESCOLA",))
    res, _ = _rodar([a], [_tx("t1", "2026-10-05", -74210, "PAGAMENTO FATURA ITAU")])
    assert res["escola:2026-10"]["estado"] == "atrasado"


def test_fatura_casa_pelo_nome_do_cartao():
    res, _ = _rodar([_fatura()], [_tx("t1", "2026-10-05", -80000, "PAGAMENTO FATURA CARTAO ITAU")])
    assert (res["cartao:2026-10"]["estado"], res["cartao:2026-10"]["metodo"]) == ("pago", "emissor")


def test_por_valor_e_pago_dentro_da_tolerancia_de_valor():
    """Por valor (|dif| <= tolerancia_valor) é pago, sem a conferência da tolerancia_fixo (R$ 0,80 > 1% de R$ 50)."""
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 5000, chaves=("ALUGUEL",))],
                        [_tx("t1", "2026-10-05", -5080, "BOLETO 123456")])
    r = res["a:2026-10"]
    assert (r["estado"], r["metodo"], r["diferenca_centavos"], r["motivo"]) == ("pago", "valor", 80, None)
    assert novos == [("t1", "a:2026-10", "valor", 80)]


# ---------- valor do casamento ----------
def test_fixo_dentro_da_tolerancia_paga():
    res, _ = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-10-05", -198000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["estado"] == "pago"


def test_fixo_a_menor_vai_a_conferir():
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-10-05", -190000, "PIX FAVORECIDO")])
    r = res["a:2026-10"]
    assert (r["estado"], r["tx_id"], r["motivo"]) == ("a_conferir", "t1", "pago a menor: R$ 1.900,00 de R$ 2.000,00")
    assert novos == []


def test_a_conferir_tira_o_lancamento_do_jogo():
    a = _comp("a:2026-10", "2026-10-05", 200000)
    b = _comp("b:2026-10", "2026-10-06", 190000, valor_tipo="variavel", valor_fonte="ultimo")
    res, _ = _rodar([a, b], [_tx("t1", "2026-10-05", -190000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["estado"] == "a_conferir" and res["b:2026-10"]["estado"] == "atrasado"


def _dia_23(hoje="2026-10-23"):
    estado = {"c1": {**ESTADO["c1"], "ult_sync_ok": f"{hoje}T14:00:00-03:00"}}
    return {"estado": estado, "hoje": dt.date.fromisoformat(hoje), "agora": dt.datetime.fromisoformat(f"{hoje}T15:00:00-03:00")}


def test_valor_conhecido_casa_antes_da_estimativa():
    """Pensão (fixo) e reembolso (sem valor) ao mesmo favorecido: o reembolso vence antes, mas não leva o Pix da pensão."""
    pensao = _comp("pensao:2026-10", "2026-10-10", 200000)
    reembolso = _comp("reembolso:2026-10", "2026-10-05", None, valor_tipo="variavel")
    txs = [_tx("t1", "2026-10-06", -200000, "PIX FAVORECIDO"), _tx("t2", "2026-10-15", -30000, "PIX FAVORECIDO")]
    res, novos = _rodar([pensao, reembolso], txs, **_dia_23("2026-10-16"))
    assert (res["pensao:2026-10"]["estado"], res["pensao:2026-10"]["tx_id"]) == ("pago", "t1")
    assert (res["reembolso:2026-10"]["estado"], res["reembolso:2026-10"]["tx_id"]) == ("pago", "t2")
    assert {(t, c) for t, c, _, _ in novos} == {("t1", "pensao:2026-10"), ("t2", "reembolso:2026-10")}


def test_valor_que_nao_encaixa_nao_rouba_o_de_quem_encaixa():
    """Pensão R$ 2.000 (05/10) e reembolso R$ 300 (12/10), um Pix de R$ 300 em 04/10: é do reembolso."""
    pensao = _comp("pensao:2026-10", "2026-10-05", 200000)
    reembolso = _comp("reembolso:2026-10", "2026-10-12", 30000)
    res, _ = _rodar([pensao, reembolso], [_tx("t1", "2026-10-04", -30000, "PIX FAVORECIDO")], **_dia_23())
    assert (res["reembolso:2026-10"]["estado"], res["reembolso:2026-10"]["tx_id"]) == ("pago", "t1")
    assert res["pensao:2026-10"]["estado"] == "atrasado"


def test_fatura_a_menor_diz_minimo():
    res, _ = _rodar([_fatura()], [_tx("t1", "2026-10-05", -10000, "PAGAMENTO FATURA CARTAO ITAU")])
    assert res["cartao:2026-10"]["motivo"] == "pago a menor (mínimo?): R$ 100,00 de R$ 800,00"


def test_fixo_acima_vai_a_conferir():
    res, _ = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-10-05", -220000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["estado"] == "a_conferir"
    assert res["a:2026-10"]["motivo"].startswith("pago acima: ")


def test_variavel_estimado_aceita_qualquer_valor():
    c = _comp("e:2026-10", "2026-10-05", 20000, valor_tipo="variavel", valor_fonte="ultimo")
    res, _ = _rodar([c], [_tx("t1", "2026-10-05", -35000, "PIX FAVORECIDO")])
    assert (res["e:2026-10"]["estado"], res["e:2026-10"]["diferenca_centavos"]) == ("pago", 15000)


def test_variavel_confirmado_a_menor_vai_a_conferir():
    c = _comp("e:2026-10", "2026-10-05", 23100, valor_tipo="variavel", valor_fonte="documento")
    res, _ = _rodar([c], [_tx("t1", "2026-10-05", -15000, "PIX FAVORECIDO")])
    assert res["e:2026-10"]["estado"] == "a_conferir" and res["e:2026-10"]["motivo"].startswith("pago a menor: ")


def test_diferenca_em_centavos():
    res, novos = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [_tx("t1", "2026-10-05", -199000, "PIX FAVORECIDO")])
    assert res["a:2026-10"]["estado"] == "pago" and res["a:2026-10"]["diferenca_centavos"] == -1000
    assert novos == [("t1", "a:2026-10", "favorecido", -1000)]


# ---------- sem lançamento ----------
def test_fatura_paid_sem_lancamento_e_pago():
    res, _ = _rodar([_fatura(payment_status="PAID")], [])
    assert (res["cartao:2026-10"]["estado"], res["cartao:2026-10"]["metodo"]) == ("pago", "banco")


def _iptu():
    return _comp("iptu:2026-10", "2026-10-01", 50000, forma="boleto", chaves=("PREFEITURA IPTU",), linha_id="iptu")


_BAIXA = {"mes": "2026-10", "compromisso": "iptu", "tipo": "pago", "valor_centavos": None, "vencimento": None,
          "data_pagamento": "2026-10-03", "origem": "manual"}


def test_baixa_manual_sem_lancamento_e_pago():
    res, novos = _rodar([_iptu()], [], pagos=[_BAIXA])
    r = res["iptu:2026-10"]
    assert (r["estado"], r["metodo"], r["tx_id"], r["pago_em"]) == ("pago", "manual", "manual:iptu:2026-10", "2026-10-03")
    assert ("manual:iptu:2026-10", "iptu:2026-10", "manual", None) in novos


def test_baixa_manual_com_lancamento_vale_o_extrato():
    res, novos = _rodar([_iptu()], [_tx("t1", "2026-10-01", -50000, "BOLETO PREFEITURA IPTU")], pagos=[_BAIXA])
    assert (res["iptu:2026-10"]["estado"], res["iptu:2026-10"]["tx_id"]) == ("pago", "t1")
    assert novos == [("t1", "iptu:2026-10", "favorecido", 0)]


def test_fatura_paid_vale_sobre_pagamento_em_partes():
    txs = [_tx("t1", "2026-10-05", -60000, "PAGAMENTO FATURA CARTAO ITAU"),
           _tx("t2", "2026-10-04", -40000, "PAGAMENTO FATURA CARTAO ITAU")]
    res, novos = _rodar([_fatura(valor=100000, payment_status="PAID")], txs)
    r = res["cartao:2026-10"]
    assert (r["estado"], r["metodo"], r["tx_id"], r["pago_em"], r["motivo"]) == ("pago", "banco", "t1", "2026-10-05", None)
    assert novos == []


def test_baixa_manual_vale_sobre_pagamento_a_menor():
    res, novos = _rodar([_iptu()], [_tx("t1", "2026-10-01", -30000, "BOLETO PREFEITURA IPTU")], pagos=[_BAIXA])
    r = res["iptu:2026-10"]
    assert (r["estado"], r["metodo"], r["tx_id"], r["motivo"]) == ("pago", "manual", "manual:iptu:2026-10", None)
    assert novos == [("manual:iptu:2026-10", "iptu:2026-10", "manual", None)]


def test_debito_automatico_vencido_sem_lancamento_fica_aberto():
    res, _ = _rodar([_comp("n:2026-10", "2026-10-05", 5590, forma="debito_automatico")], [])
    assert res["n:2026-10"]["estado"] == "aberto"


def test_extrato_parado_vira_a_conferir():
    estado = {"c1": {**ESTADO["c1"], "ult_sync_ok": "2026-10-05T10:00:00-03:00"}}
    res, _ = _rodar([_comp("a:2026-10", "2026-10-05", 200000)], [], estado=estado)
    assert (res["a:2026-10"]["estado"], res["a:2026-10"]["motivo"]) == ("a_conferir", "extrato parado desde 05/10")


def test_vencido_sem_nada_e_atrasado():
    res, _ = _rodar([_comp("a:2026-10", "2026-10-07", 200000)], [])
    assert res["a:2026-10"]["estado"] == "atrasado"


def test_nao_vencido_e_aberto():
    comps = [_comp("a:2026-10", "2026-10-08", 200000),
             _comp("e:2026-10", "2026-10-15", 20000, valor_tipo="variavel", valor_fonte="ultimo"),
             _comp("s:2026-10", "2026-10-20", None, valor_tipo="variavel")]
    res, _ = _rodar(comps, [])
    assert {r["estado"] for r in res.values()} == {"aberto"}


def test_nunca_ha_previsto_nem_debito_automatico():
    comps = [_comp("a:2026-10", "2026-10-05", 200000), _comp("n:2026-10", "2026-10-05", 5590, forma="debito_automatico"),
             _comp("n:2026-11", "2026-11-05", 5590, forma="debito_automatico"),
             _comp("e:2026-11", "2026-11-15", 20000, valor_tipo="variavel", valor_fonte="ultimo"),
             _comp("s:2026-11", "2026-11-20", None, valor_tipo="variavel"), _fatura(payment_status="PAID"), _iptu()]
    res, _ = _rodar(comps, [_tx("t1", "2026-10-05", -190000, "PIX FAVORECIDO")], pagos=[_BAIXA])
    assert {r["estado"] for r in res.values()} <= ESTADOS
    assert all(set(r) == {"estado", "metodo", "tx_id", "pago_em", "diferenca_centavos", "motivo"} for r in res.values())
