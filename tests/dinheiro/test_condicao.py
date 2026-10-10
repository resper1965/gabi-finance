import datetime as dt
import json

import pytest

from gabi.dinheiro import classificar
from gabi.dinheiro.condicao import confere, validar
from gabi.dinheiro.regras import aprovar, contar_afetados, criar_regra_ativa, criar_sugestao, definir_ativa
from tests.dinheiro.test_regras import _get, _l, con  # noqa: F401  (fixture)

HOJE = dt.date(2026, 10, 8)


def _lanc(**k):
    return {"conta_id": 1, "valor_centavos": -2500, "data": "2026-10-10", **k}  # 10/10/2026 é sábado (5)


def test_sem_condicao_sempre_confere():
    assert confere(None, _lanc())


def test_conta_valor_e_dia_da_semana():
    assert confere({"conta_id": [1, 2]}, _lanc()) and not confere({"conta_id": [3]}, _lanc())
    assert confere({"valor_min": 2000, "valor_max": 3000}, _lanc()) and not confere({"valor_max": 2000}, _lanc())
    assert confere({"valor_min": 2500}, _lanc(valor_centavos=2500))  # entrada e saída: vale o valor absoluto
    assert confere({"dias_semana": [5, 6]}, _lanc()) and not confere({"dias_semana": [0]}, _lanc())


def test_todas_as_chaves_precisam_conferir():
    assert not confere({"conta_id": [1], "dias_semana": [0]}, _lanc())


@pytest.mark.parametrize("ruim", [{"cor": 1}, {"conta_id": []}, {"conta_id": "1"}, {"valor_min": -1}, {"valor_min": 5, "valor_max": 1},
                                  {"dias_semana": [7]}, {"dias_semana": [1.5]}, "x", []])
def test_validar_recusa_condicao_invalida(ruim):
    with pytest.raises(ValueError):
        validar(ruim)


def test_validar_normaliza_e_vazio_vira_none():
    assert validar(None) is None and validar({}) is None
    assert validar({"conta_id": 1}) == {"conta_id": [1]}


def test_regra_com_condicao_so_pega_o_que_confere(con):
    a = _l(con, 1, data="2026-10-10")  # sábado
    b = _l(con, 2, data="2026-10-09")  # sexta
    rid = criar_regra_ativa(con, "UBER", {"categoria_id": 2}, "boss", condicao={"dias_semana": [5]})
    assert _get(con, a)["categoria_id"] == 2 and _get(con, b)["categoria_id"] is None
    assert json.loads(con.execute("select condicao from regra where id=?", (rid,)).fetchone()[0]) == {"dias_semana": [5]}


def test_mesmo_padrao_com_condicoes_diferentes_nao_e_duplicata(con):
    assert criar_regra_ativa(con, "UBER", {"categoria_id": 2}, "boss", condicao={"dias_semana": [5]})
    assert criar_regra_ativa(con, "UBER", {"categoria_id": 3}, "boss", condicao={"dias_semana": [0]})
    assert criar_regra_ativa(con, "UBER", {"categoria_id": 2}, "boss", condicao={"dias_semana": [5]}) is None


def test_classificador_respeita_a_condicao_e_a_regra_sem_condicao_continua_valendo(con):
    criar_regra_ativa(con, "UBER", {"categoria_id": 2}, "boss", condicao={"valor_min": 5000})
    criar_regra_ativa(con, "UBER", {"categoria_id": 3}, "boss")
    barato, caro = _l(con, 1, valor_centavos=-1000), _l(con, 2, valor_centavos=-9000)
    classificar.classificar(con, barato)
    classificar.classificar(con, caro)
    assert (_get(con, barato)["categoria_id"], _get(con, caro)["categoria_id"]) == (3, 2)


def test_aprovar_sugestao_com_condicao_cria_regra_com_condicao(con):
    sid = criar_sugestao(con, "regra", None, {"padrao": "UBER", "acao": {"categoria_id": 2}, "condicao": {"conta_id": [1]}}, "x")
    rid = aprovar(con, sid, None, "boss")
    assert json.loads(con.execute("select condicao from regra where id=?", (rid,)).fetchone()[0]) == {"conta_id": [1]}


def test_condicao_invalida_na_aprovacao_recusa(con):
    sid = criar_sugestao(con, "regra", None, {"padrao": "UBER", "acao": {"categoria_id": 2}, "condicao": {"dias_semana": [9]}}, "x")
    with pytest.raises(ValueError):
        aprovar(con, sid, None, "boss")


def test_previa_conta_so_os_que_conferem(con):
    _l(con, 1, data="2026-10-10"), _l(con, 2, data="2026-10-09")
    assert contar_afetados(con, "UBER", {"categoria_id": 2}, HOJE, condicao={"dias_semana": [5]})["passado"] == 1


def test_ligar_regra_com_condicao_aplica_so_o_que_confere(con):
    a, b = _l(con, 1, data="2026-10-10"), _l(con, 2, data="2026-10-09")
    con.execute("insert into regra(padrao, acao, ativa, criado_em, condicao) values ('UBER','{\"categoria_id\": 2}',0,'2026-10-01T00:00:00','{\"dias_semana\":[5]}')")
    definir_ativa(con, 1, True, "boss")
    assert _get(con, a)["categoria_id"] == 2 and _get(con, b)["categoria_id"] is None
