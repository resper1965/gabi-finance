"""API /api/v1/atividades: cada rota só chama gabi.atividades (hoje = 08/10/2026 nas fixtures de test_cadastros_api)."""
import pytest

from gabi.db import conectar
from tests.rotas.test_cadastros_api import BOSS, VIP, banco, cli, req  # noqa: F401  (fixtures do cliente HTTP)


def _criar(cli, texto="ligar pro contador", **extra):
    r = req(cli, "POST", "/api/v1/atividades", {"texto": texto, **extra})
    assert r.status_code == 201, r.text
    return r.json()["dados"]


def _lista(cli, status="aberta"):
    return req(cli, "GET", f"/api/v1/atividades?status={status}").json()["dados"]["itens"]


def test_vip_nao_acessa(cli):
    assert req(cli, "GET", "/api/v1/atividades", h=VIP).status_code == 403
    assert req(cli, "POST", "/api/v1/atividades", {"texto": "x"}, h=VIP).status_code == 403


def test_criar_aparece_na_lista_e_grava_decisao_do_painel(cli, banco):
    a = _criar(cli, vence_em="2026-10-30T10:00")
    assert a["status"] == "aberta" and a["vence_em"] == "2026-10-30T10:00"
    assert [i["id"] for i in _lista(cli)] == [a["id"]]
    assert tuple(conectar(banco).execute("select quem, origem from decisao where o_que like 'atividade%'").fetchone()) == ("boss@x.com", "painel")


def test_status_invalido_e_400(cli):
    assert req(cli, "GET", "/api/v1/atividades?status=lixo").status_code == 400


def test_concluir_sai_das_abertas_e_entra_nas_feitas(cli):
    a = _criar(cli)
    assert req(cli, "POST", f"/api/v1/atividades/{a['id']}/concluir").status_code == 200
    assert _lista(cli) == [] and [i["id"] for i in _lista(cli, "feita")] == [a["id"]]


def test_cancelar_e_cancelar_depois_de_concluir_e_400(cli):
    a, b = _criar(cli, "a"), _criar(cli, "b")
    assert req(cli, "POST", f"/api/v1/atividades/{a['id']}/cancelar").json()["dados"]["status"] == "cancelada"
    req(cli, "POST", f"/api/v1/atividades/{b['id']}/concluir")
    assert req(cli, "POST", f"/api/v1/atividades/{b['id']}/cancelar").status_code == 400


def test_id_inexistente_e_404(cli):
    assert req(cli, "POST", "/api/v1/atividades/999/concluir").status_code == 404
    assert req(cli, "PATCH", "/api/v1/atividades/999", {"vence_em": "2026-12-01"}).status_code == 404


def test_adiar_com_patch_e_passado_e_400(cli):
    a = _criar(cli, vence_em="2026-10-30")
    r = req(cli, "PATCH", f"/api/v1/atividades/{a['id']}", {"vence_em": "2026-11-02T09:30"})
    assert r.status_code == 200 and r.json()["dados"]["vence_em"] == "2026-11-02T09:30"
    assert req(cli, "PATCH", f"/api/v1/atividades/{a['id']}", {"vence_em": "2026-10-01"}).status_code == 400


@pytest.mark.parametrize("corpo", [{}, {"texto": ""}, {"texto": "x", "extra": 1}, {"texto": 5}, {"texto": "x", "vence_em": 7}])
def test_corpo_invalido_e_400(cli, corpo):
    assert req(cli, "POST", "/api/v1/atividades", corpo).status_code == 400
