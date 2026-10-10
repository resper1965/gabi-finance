import json

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.paperless import ErroPaperless
from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, get, post  # noqa: F401  (fixtures)

SEGREDO = "tok-secreto-123"


class PaperlessOk:
    def docs(self, **f):
        return [{"id": 1}]


class PaperlessRuim:
    def docs(self, **f):
        raise ErroPaperless("GET /api/documents/ -> 401")


class NiboOk:
    def organizations(self):
        return [{"name": "Bekaa"}]


def _cli(banco, **fontes):
    app = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes=fontes)
    app.state.saude = None
    return TestClient(app, client=("127.0.0.1", 50000))


def test_lista_os_7_passos_na_ordem_com_explicacao_em_portugues(banco):
    d = get(_cli(banco), "/api/v1/setup").json()["dados"]["passos"]
    assert [p["passo"] for p in d] == ["microsoft", "bancos", "paperless", "nibo", "extras", "canal", "pronto"]
    assert all(p["titulo"] and p["explicacao"] and p["estado"] == "pendente" for p in d)


def test_credencial_valida_testa_na_hora_e_marca_feito(banco):
    cli = _cli(banco, paperless=lambda: PaperlessOk())
    r = post(cli, "/api/v1/setup/paperless", {"acao": "testar"}).json()["dados"]
    assert r["ok"] is True and r["estado"] == "feito"
    assert [p["estado"] for p in get(cli, "/api/v1/setup").json()["dados"]["passos"] if p["passo"] == "paperless"] == ["feito"]


def test_credencial_invalida_devolve_ok_false_com_detalhe_e_nao_marca_feito(banco):
    cli = _cli(banco, paperless=lambda: PaperlessRuim())
    r = post(cli, "/api/v1/setup/paperless", {"acao": "testar"}).json()["dados"]
    assert r["ok"] is False and "401" in r["detalhe"] and r["estado"] == "pendente"


def test_fonte_nao_configurada_diz_onde_colocar_a_credencial(banco):
    r = post(_cli(banco, nibo=lambda: None), "/api/v1/setup/nibo", {"acao": "testar"}).json()["dados"]
    assert r["ok"] is False and "/etc/gabi/cobrar.env" in r["detalhe"]


def test_nibo_ok(banco):
    assert post(_cli(banco, nibo=lambda: NiboOk()), "/api/v1/setup/nibo", {"acao": "testar"}).json()["dados"]["ok"] is True


def test_passo_pode_ficar_para_depois_e_progresso_persiste(banco):
    post(_cli(banco), "/api/v1/setup/canal", {"acao": "depois"})
    novo = _cli(banco)  # outra "execução" do app: o progresso vem do banco
    assert [p["estado"] for p in get(novo, "/api/v1/setup").json()["dados"]["passos"] if p["passo"] == "canal"] == ["depois"]


def test_bancos_olha_a_ultima_rodada_conferida(banco):
    cli = _cli(banco)
    r = post(cli, "/api/v1/setup/bancos", {"acao": "testar"}).json()["dados"]
    assert r["ok"] is True  # o banco de teste traz uma rodada open-finance conferida
    c = conectar(banco)
    c.execute("update rodada set conferida=0")
    c.close()
    assert post(cli, "/api/v1/setup/bancos", {"acao": "testar"}).json()["dados"]["ok"] is False


def test_pronto_so_fecha_quando_todos_os_outros_estao_feitos_ou_para_depois(banco):
    cli = _cli(banco, paperless=lambda: PaperlessOk(), nibo=lambda: NiboOk())
    assert post(cli, "/api/v1/setup/pronto", {"acao": "testar"}).json()["dados"]["ok"] is False
    for p in ("microsoft", "bancos", "extras", "canal"):
        post(cli, f"/api/v1/setup/{p}", {"acao": "depois"})
    post(cli, "/api/v1/setup/paperless", {"acao": "testar"})
    post(cli, "/api/v1/setup/nibo", {"acao": "testar"})
    assert post(cli, "/api/v1/setup/pronto", {"acao": "testar"}).json()["dados"]["ok"] is True


def test_nenhum_segredo_em_resposta_nem_no_banco(banco, monkeypatch):
    monkeypatch.setenv("PAPERLESS_TOKEN", SEGREDO)
    monkeypatch.setenv("NIBO_TOKEN", SEGREDO)
    cli = _cli(banco, paperless=lambda: PaperlessRuim(), nibo=lambda: None)
    corpos = [post(cli, "/api/v1/setup/paperless", {"acao": "testar"}).text, post(cli, "/api/v1/setup/nibo", {"acao": "testar"}).text, get(cli, "/api/v1/setup").text]
    assert SEGREDO not in "".join(corpos)
    c = conectar(banco)
    assert SEGREDO not in json.dumps([tuple(r) for r in c.execute("select * from setup_passo")])


def test_passo_inexistente_acao_invalida_e_so_boss(banco):
    cli = _cli(banco)
    assert post(cli, "/api/v1/setup/xyz", {"acao": "testar"}).status_code == 404
    assert post(cli, "/api/v1/setup/nibo", {"acao": "apagar"}).status_code == 400
    assert get(cli, "/api/v1/setup", VIP).status_code == 403
