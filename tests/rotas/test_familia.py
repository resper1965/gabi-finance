import json
import threading

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.familia.saude import abrir_saude
from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, get, post  # noqa: F401  (fixtures)

CHAVE = bytes(range(32))
LAUDO = "Paciente: Ana   Data da coleta: 10/07/2026\nColesterol total ... 215 mg/dL Valor de referência: 0 a 200 mg/dL\nGlicose: 92 mg/dL\n"


class PaperlessFalso:
    def __init__(self):
        self.pedidos = []

    def docs(self, **f):
        self.pedidos.append(f)
        return [{"id": f["id"], "content": LAUDO, "created": "2026-07-11T10:00:00-03:00"}] if f.get("id") == 55 else []


@pytest.fixture
def app(banco, tmp_path):
    c = conectar(banco)
    c.execute("insert into matriz_acesso(informacao, boss, familia_vip, terceiros) values ('saúde','total','parcial','nenhum')")
    c.execute("insert into pessoa(id, nome) values ('p2','Maria')")
    c.close()
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"paperless": lambda: PaperlessFalso()})
    a.state.saude = (tmp_path / "saude.enc", CHAVE)
    return a


@pytest.fixture
def cli(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def _semear(app):
    with abrir_saude(*app.state.saude) as s:
        from gabi.familia.saude import registrar_exame
        import datetime as dt
        registrar_exame(s, "p2", "Colesterol total", "190", "mg/dL", dt.date(2026, 1, 1), ("0", "200"), 1, "boss@x.com")  # p2 = vip@x.com
        registrar_exame(s, "p9", "Colesterol total", "150", "mg/dL", dt.date(2026, 1, 1), ("0", "200"), 2, "boss@x.com")


def test_sem_chave_configurada_da_503(banco):
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={})
    a.state.saude = None
    r = TestClient(a, client=("127.0.0.1", 50000)).get("/api/v1/familia/pessoas", headers=BOSS)
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def test_boss_ve_todas_as_pessoas_e_o_familiar_so_a_propria(app, cli):
    _semear(app)
    assert {p["id"] for p in get(cli, "/api/v1/familia/pessoas").json()["dados"]["itens"]} == {"p1", "p2", "p9"}
    assert {p["id"] for p in get(cli, "/api/v1/familia/pessoas", VIP).json()["dados"]["itens"]} == {"p2"}


def test_familiar_nao_ve_pasta_de_outro(app, cli):
    _semear(app)
    assert get(cli, "/api/v1/familia/exames/p2", VIP).status_code == 200
    assert get(cli, "/api/v1/familia/exames/p9", VIP).status_code == 403
    assert get(cli, "/api/v1/familia/exames/p9/serie?marcador=Colesterol total", VIP).status_code == 403
    assert get(cli, "/api/v1/familia/exames/p9/resumo", VIP).status_code == 403


def test_terceiro_e_quem_nao_tem_matriz_nao_alcancam(app, cli, banco):
    c = conectar(banco)
    c.execute("update matriz_acesso set familia_vip='nenhum'")
    c.close()
    assert get(cli, "/api/v1/familia/exames/p2", VIP).status_code == 403
    assert cli.get("/api/v1/familia/pessoas").status_code == 401


def test_marcadores_serie_e_resumo_do_boss(app, cli):
    _semear(app)
    d = get(cli, "/api/v1/familia/exames/p2").json()["dados"]
    assert d["marcadores"][0]["marcador"] == "Colesterol total" and d["marcadores"][0]["valor"] == "190"
    s = get(cli, "/api/v1/familia/exames/p2/serie?marcador=Colesterol total").json()["dados"]
    assert [p["valor"] for p in s["pontos"]] == ["190"] and s["pontos"][0]["fora_da_faixa"] is False
    assert "Colesterol total" in get(cli, "/api/v1/familia/exames/p2/resumo").json()["dados"]["texto"]


def test_leitura_pela_api_fica_registrada_com_o_login(app, cli):
    _semear(app)
    get(cli, "/api/v1/familia/exames/p2/resumo", VIP)
    with abrir_saude(*app.state.saude) as s:
        assert ("vip@x.com", "p2", "resumo") in [tuple(r) for r in s.con.execute("select quem, pessoa_id, o_que from leitura")]


def test_fluxo_de_laudo_ler_confirmar_e_aparecer(app, cli):
    r = post(cli, "/api/v1/familia/laudos", {"paperless_id": 55, "pessoa_sugerida": "p2"})
    assert r.status_code == 201 and r.json()["dados"]["propostas"] == 2
    assert get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"] == []  # só proposta
    pend = get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"]
    assert pend[0]["paperless_id"] == 55 and {m["marcador"] for m in pend[0]["marcadores"]} == {"Colesterol total", "Glicose"}
    assert post(cli, "/api/v1/familia/laudos/55/confirmar", {}).status_code == 400  # sem a pessoa
    assert post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"}).json()["dados"]["exames"] == 2
    assert len(get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"]) == 2


def test_laudo_e_so_do_boss_e_documento_inexistente_da_404(app, cli):
    assert post(cli, "/api/v1/familia/laudos", {"paperless_id": 55}, VIP).status_code == 403
    assert post(cli, "/api/v1/familia/laudos", {"paperless_id": 999}).status_code == 404


def test_rejeitar_laudo_descarta(app, cli):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    assert post(cli, "/api/v1/familia/laudos/55/rejeitar", {}).json()["dados"]["rejeitadas"] == 2
    assert get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"] == []
