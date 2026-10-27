"""API /api/v1/despesas: cada rota só chama gabi.dinheiro.despesas; o efeito aparece na hora em /contas-pagar."""
import pytest

from gabi.db import conectar
from tests.rotas.test_cadastros_api import BOSS, VIP, banco, cli, req  # noqa: F401  (fixtures do cliente HTTP; hoje = 08/10/2026)

ESCOLA = {"tipo": "fixa", "nome": "Escola", "valor_padrao": "3000.00", "vencimento": "dia:20"}


def _a_pagar(cli) -> dict:
    d = req(cli, "GET", "/api/v1/contas-pagar").json()["dados"]
    return {i["id"]: i for g in d.values() for i in g}


def _escola(cli):
    r = req(cli, "POST", "/api/v1/despesas", ESCOLA)
    assert r.status_code == 201, r.text
    return r.json()["dados"]


def test_vip_nao_acessa(cli):
    assert req(cli, "GET", "/api/v1/despesas", h=VIP).status_code == 403
    assert req(cli, "POST", "/api/v1/despesas", ESCOLA, h=VIP).status_code == 403


def test_criar_fixa_lista_e_entra_em_a_pagar(cli, banco):
    d = _escola(cli)
    assert d["id"] == "escola" and d["valor"] == "3000.00" and d["tipo"] == "fixa"
    oc = _a_pagar(cli)["escola:2026-10"]
    assert (oc["linha_id"], oc["mes"], oc["tipo"], oc["valor"]) == ("escola", "2026-10", "fixa", "3000.00")
    r = req(cli, "GET", "/api/v1/despesas?tipo=fixa&situacao=ativa")
    assert r.status_code == 200 and [i["id"] for i in r.json()["dados"]["itens"]] == ["escola"]
    assert req(cli, "GET", "/api/v1/despesas?tipo=avulsa").json()["dados"]["itens"] == []
    assert conectar(banco).execute("select quem, origem from decisao where o_que like 'despesa escola%'").fetchone()[:] == ("boss@x.com", "painel")


def test_criar_avulsa(cli):
    r = req(cli, "POST", "/api/v1/despesas", {"tipo": "avulsa", "data": "2026-10-25", "nome": "Dentista", "valor_padrao": "450.00"})
    assert r.status_code == 201 and r.json()["dados"]["tipo"] == "avulsa"
    oc = _a_pagar(cli)["dentista-202610:2026-10"]
    assert (oc["linha_id"], oc["mes"], oc["tipo"], oc["valor"]) == ("dentista-202610", "2026-10", "avulsa", "450.00")
    assert not any(k.startswith("dentista-202610:2026-11") for k in _a_pagar(cli))


@pytest.mark.parametrize("corpo", [{**ESCOLA, "tipo": "outra"}, {**ESCOLA, "tipo": "avulsa"}, {**ESCOLA, "data": "2026-10-20"},
                                   {**ESCOLA, "vencimento": "dia:40"}, {**ESCOLA, "estranho": 1}, {**ESCOLA, "nome": " "},
                                   {"tipo": "avulsa", "data": "20/10/2026", "nome": "X", "valor_padrao": "1.00"}, []])
def test_criar_invalido_400(cli, banco, corpo):
    r = req(cli, "POST", "/api/v1/despesas", corpo)
    assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida"
    assert conectar(banco).execute("select count(*) from compromisso_linha").fetchone()[0] == 0


def test_listar_filtro_invalido_400(cli):
    assert req(cli, "GET", "/api/v1/despesas?tipo=x").status_code == 400
    assert req(cli, "GET", "/api/v1/despesas?situacao=x").status_code == 400


def test_mudar_daqui_em_diante(cli):
    _escola(cli)
    r = req(cli, "PATCH", "/api/v1/despesas/escola", {"valor_padrao": "3500.00"})
    assert r.status_code == 200 and r.json()["dados"]["valor"] == "3500.00" and r.json()["dados"]["a_partir"] == "2026-10"
    assert _a_pagar(cli)["escola:2026-10"]["valor"] == "3500.00"


def test_mudar_a_partir(cli):
    _escola(cli)
    r = req(cli, "PATCH", "/api/v1/despesas/escola", {"valor_padrao": "3500.00", "a_partir": "2026-11"})
    assert r.status_code == 200 and r.json()["dados"]["nova_versao"] is True
    ap = _a_pagar(cli)
    assert ap["escola:2026-10"]["valor"] == "3000.00" and ap["escola-202611:2026-11"]["valor"] == "3500.00"
    assert ap["escola-202611:2026-11"]["linha_id"] == "escola-202611"


def test_mudar_invalido_400(cli):
    _escola(cli)
    for corpo in ({"estranho": 1}, {"vencimento": "dia:40"}, {"a_partir": "2026-13"}, {"a_partir": "2026-09"}):
        r = req(cli, "PATCH", "/api/v1/despesas/escola", corpo)
        assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida", corpo


def test_mudar_um_mes(cli):
    _escola(cli)
    r = req(cli, "POST", "/api/v1/despesas/escola/mes/2026-11", {"valor": "100.00", "vencimento": "2026-11-25"})
    assert r.status_code == 200 and r.json()["dados"]["mes"] == "2026-11"
    oc = _a_pagar(cli)["escola:2026-11"]
    assert oc["valor"] == "100.00" and oc["vencimento"] == "2026-11-25"
    assert _a_pagar(cli)["escola:2026-10"]["valor"] == "3000.00"
    assert req(cli, "POST", "/api/v1/despesas/escola/mes/2026-11", {}).status_code == 400
    assert req(cli, "POST", "/api/v1/despesas/escola/mes/2026-11", {"valor": "1", "x": 1}).status_code == 400
    assert req(cli, "POST", "/api/v1/despesas/escola/mes/2026-13", {"valor": "1"}).status_code == 400


def test_dispensar_e_desfazer(cli):
    _escola(cli)
    r = req(cli, "POST", "/api/v1/despesas/escola/mes/2026-11/dispensar")
    assert r.status_code == 200 and r.json()["dados"]["dispensado"] is True
    assert "escola:2026-11" not in _a_pagar(cli) and "escola:2026-10" in _a_pagar(cli)
    r = req(cli, "DELETE", "/api/v1/despesas/escola/mes/2026-11/dispensar")
    assert r.status_code == 200 and r.json()["dados"]["dispensado"] is False
    assert "escola:2026-11" in _a_pagar(cli)
    assert req(cli, "DELETE", "/api/v1/despesas/escola/mes/2026-11/dispensar").status_code == 404


def test_encerrar(cli):
    _escola(cli)
    r = req(cli, "POST", "/api/v1/despesas/escola/encerrar", {"ultimo_mes": "2026-10"})
    assert r.status_code == 200 and r.json()["dados"] == {"id": "escola", "ultimo_mes": "2026-10"}
    ap = _a_pagar(cli)
    assert "escola:2026-11" not in ap and "escola:2026-10" in ap
    assert req(cli, "POST", "/api/v1/despesas/escola/encerrar", {"ultimo_mes": "outubro"}).status_code == 400
    assert req(cli, "POST", "/api/v1/despesas/escola/encerrar", {"x": 1}).status_code == 400


def test_encerrar_sem_corpo_usa_o_padrao(cli):
    _escola(cli)
    r = req(cli, "POST", "/api/v1/despesas/escola/encerrar")
    assert r.status_code == 200 and r.json()["dados"]["ultimo_mes"] == "2026-09"
    assert not any(k.startswith("escola:") for k in _a_pagar(cli))


def test_excluir(cli):
    _escola(cli)
    r = req(cli, "DELETE", "/api/v1/despesas/escola")
    assert r.status_code == 200 and r.json()["dados"] == {"id": "escola", "excluida": True, "encerrada": False}
    assert not any(k.startswith("escola:") for k in _a_pagar(cli))
    assert req(cli, "GET", "/api/v1/despesas").json()["dados"]["itens"] == []


def test_excluir_com_pagamento_vira_encerrar(cli, banco):
    _escola(cli)
    assert req(cli, "POST", "/api/v1/contas-pagar/escola:2026-10/paga").status_code == 200
    r = req(cli, "DELETE", "/api/v1/despesas/escola")
    assert r.status_code == 200 and r.json()["dados"]["encerrada"] is True and r.json()["dados"]["excluida"] is False


@pytest.mark.parametrize("metodo,url,corpo", [("PATCH", "/api/v1/despesas/nada", {"valor_padrao": "1.00"}), ("DELETE", "/api/v1/despesas/nada", None),
                                              ("POST", "/api/v1/despesas/nada/encerrar", None), ("POST", "/api/v1/despesas/nada/mes/2026-10", {"valor": "1"}),
                                              ("POST", "/api/v1/despesas/nada/mes/2026-10/dispensar", None)])
def test_404_nao_encontrado(cli, metodo, url, corpo):
    r = req(cli, metodo, url, corpo)
    assert r.status_code == 404 and r.json()["erro"] == "nao_encontrado"
