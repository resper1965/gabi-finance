from gabi.cobrar import cobranca, comprovantes, lote_nibo, pedidos, recebimentos, reembolso, util


def test_brl_e_agora_tem_uma_implementacao_so():
    assert util.brl(123456) == "R$ 1.234,56" and util.brl(5) == "R$ 0,05"
    assert util.agora().endswith("+00:00")
    assert comprovantes._brl is lote_nibo._brl is cobranca._brl is util.brl
    assert comprovantes._agora is reembolso._agora is lote_nibo._agora is recebimentos._agora is pedidos._agora is util.agora
