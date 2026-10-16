import datetime as dt

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.familia.saude import abrir_saude
from gabi.reembolso_saude import cofre
from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, get, post  # noqa: F401  (fixtures)

CHAVE = bytes(range(32))


@pytest.fixture
def app(banco, tmp_path):
    c = conectar(banco)
    c.execute("insert into matriz_acesso(informacao, boss, familia_vip, terceiros) values ('saúde','total','parcial','nenhum')")
    c.close()
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={})
    a.state.saude = (tmp_path / "saude.enc", CHAVE)
    return a


@pytest.fixture
def cli(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def _semear(app):
    with abrir_saude(*app.state.saude) as s:
        for i, tipo in ((10, "nf"), (11, "comprovante")):
            cofre.gravar_doc(s, {"id": i, "estado": "a_pedir", "documento": tipo, "caso": "consulta", "data": dt.date(2026, 10, 3), "adicionado": dt.date(2026, 10, 4),
                                 "campos": {"paciente": "Bia Souza", "prestador": "Dra. Ana Lima", "valor": "300.00"}})


def test_boss_ve_dossies_com_nomes_e_o_acesso_fica_no_log(app, cli):
    _semear(app)
    d = cli.get("/api/v1/reembolso-saude/dossies", headers=BOSS).json()["dados"]
    (x,) = d["dossies"]
    assert (x["dossie"], x["paciente"], x["prestador"], x["mes"], x["estado"]) == (1, "Bia Souza", "Dra. Ana Lima", "2026-10", "a_pedir")
    assert [(y["id"], y["documento"], y["estado"]) for y in x["documentos"]] == [(10, "nf", "a_pedir"), (11, "comprovante", "a_pedir")]
    assert "valor" not in str(x) and "300" not in str(x) and "comprovante" not in x["faltam"] and "CRM/CRP" in x["faltam"]
    with abrir_saude(*app.state.saude) as s:
        assert s.con.execute("select count(*) from leitura where o_que='reembolso:dossies'").fetchone()[0] == 1


def test_so_boss_com_grau_total(app, cli):
    _semear(app)
    assert cli.get("/api/v1/reembolso-saude/dossies", headers=VIP).status_code == 403


def test_sem_chave_da_503(banco):
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={})
    a.state.saude = None
    r = TestClient(a, client=("127.0.0.1", 50000)).get("/api/v1/reembolso-saude/dossies", headers=BOSS)
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def _projecao(banco, estado="a_pedir"):
    c = conectar(banco)
    c.execute("insert into reembolso_saude_dossie(id, mes, estado, docs, pronto, faltam, doc_ids, parado_desde, atualizado_em) values (1,'2026-10',?,2,0,'[\"conselho\"]','[10,11]','2026-10-04','2026-10-16T00:00:00+00:00')", (estado,))
    c.close()


def test_dossies_trazem_parado_desde(app, cli, banco):
    _semear(app)
    _projecao(banco)
    assert cli.get("/api/v1/reembolso-saude/dossies", headers=BOSS).json()["dados"]["dossies"][0]["parado_desde"] == "2026-10-04"


def test_semana_devolve_o_texto_da_lista_sem_nomes(app, cli, banco):
    _projecao(banco)
    d = get(cli, "/api/v1/reembolso-saude/semana").json()["dados"]
    assert d["texto"] == "\n".join(d["linhas"]) and "Dossiê 1 (10/2026)" in d["texto"] and "Bia" not in d["texto"]
    assert get(cli, "/api/v1/reembolso-saude/semana", VIP).status_code == 403


def test_pedi_e_recebi_gravam_so_a_intencao(app, cli, banco):
    _projecao(banco)
    r = post(cli, "/api/v1/reembolso-saude/dossies/1/pedi", {"protocolo": "AB-123"})
    assert r.status_code == 200 and r.json()["dados"]["registrado"] is True
    assert post(cli, "/api/v1/reembolso-saude/dossies/1/pedi", {}).json()["dados"]["ja_registrado"] is True
    c = conectar(banco)
    assert [tuple(x) for x in c.execute("select dossie_id, acao, protocolo, aplicado_em from reembolso_saude_acao")] == [(1, "pedi", "AB-123", None)]
    assert c.execute("select estado from reembolso_saude_dossie").fetchone()[0] == "a_pedir"  # o estado só muda na rodada
    assert post(cli, "/api/v1/reembolso-saude/dossies/1/recebi", {}).status_code == 400  # ainda não está pedido
    c.execute("update reembolso_saude_dossie set estado='pedido'")
    assert post(cli, "/api/v1/reembolso-saude/dossies/1/recebi", {}).status_code == 200
    assert post(cli, "/api/v1/reembolso-saude/dossies/9/pedi", {}).status_code == 404


def test_pedi_e_recebi_so_boss_total(banco, cli):
    _projecao(banco)
    assert post(cli, "/api/v1/reembolso-saude/dossies/1/pedi", {}, VIP).status_code == 403
    assert post(cli, "/api/v1/reembolso-saude/dossies/1/recebi", {}, {"Tailscale-User-Login": "estranho@x.com"}).status_code == 403
