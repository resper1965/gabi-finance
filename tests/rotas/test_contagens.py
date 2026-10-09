from gabi.db import conectar
from gabi.dinheiro.regras import criar_sugestao

from tests.rotas.test_dinheiro_api import BOSS, VIP, banco, cli, get  # noqa: F401  (fixtures)


def _sugerir(banco, n):
    c = conectar(banco)
    for i in range(n):
        criar_sugestao(c, "regra", None, {"padrao": f"X{i}", "acao": {"categoria_id": 2}}, "Gabi sugere")
    c.close()


def test_contagem_de_sugestoes_igual_a_lista(cli, banco):
    _sugerir(banco, 3)
    lista = get(cli, "/api/v1/sugestoes").json()["dados"]["itens"]
    cont = get(cli, "/api/v1/contagens").json()["dados"]
    assert cont["menu"]["regras"] == len(lista) == 3


def test_contagem_de_pagar_soma_atrasadas_e_a_conferir(cli):
    grupos = get(cli, "/api/v1/contas-pagar").json()["dados"]
    esperado = len(grupos["atrasadas"]) + len(grupos["a_conferir"])
    assert esperado == 2  # IPTU atrasado + Mensalidade a conferir (fixture)
    assert get(cli, "/api/v1/contagens").json()["dados"]["menu"]["caixa"] == esperado


def test_sino_e_a_soma_dos_selos(cli, banco):
    _sugerir(banco, 2)
    d = get(cli, "/api/v1/contagens").json()["dados"]
    assert d["sino"] == sum(d["menu"].values()) and d["sino"] >= 4


def test_contagens_so_boss(cli):
    assert get(cli, "/api/v1/contagens", VIP).status_code == 403
