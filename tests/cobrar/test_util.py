from gabi.cobrar import recebimentos, util


def test_brl_e_agora_tem_uma_implementacao_so():
    assert util.brl(123456) == "R$ 1.234,56" and util.brl(5) == "R$ 0,05"
    assert util.agora().endswith("+00:00")
    assert recebimentos._agora is util.agora
