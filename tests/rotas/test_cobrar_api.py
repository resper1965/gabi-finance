import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from tests.cobrar.test_lote_nibo import NiboFalso

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
AGORA = dt.datetime(2026, 10, 9, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
JSON = {"Content-Type": "application/json"}


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")   # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj','C6','BANK','C6 PJ',1,'sim')")       # 2
    c.execute("insert into empresa(id, nome, dados) values ('ness','Ness', ?)", (json.dumps({"relacao": "contratante", "email_cobranca": "fin@ness.com.br"}),))
    c.execute("insert into empresa(id, nome, dados) values ('bekaa','Bekaa','{\"relacao\": \"pj_titular\"}')")
    c.execute("insert into categoria(nome, nibo_category_id) values ('Software','cat-sw')")
    c.execute("insert into parametro(chave, valor) values ('nibo_socio_id', '\"socio\"')")
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps({"canais": ["whatsapp:+5511911110000"], "pode_pedir": True}),))
    for i, (d, v, emp, desc) in enumerate([("2026-10-01", -10000, "ness", "HOTEL"), ("2026-10-02", -5000, "ness", "TAXI"), ("2026-10-03", -7000, "bekaa", "LICENCA")], 1):
        c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, categoria_id, status) "
                  "values (1,?,?,?,?,?,?,1,'posted')", (f"l{i}", d, v, desc, desc, emp))
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-09T17:00:00+00:00','2026-10-09T17:00:30+00:00','ok',1)")
    c.close()
    return p


@pytest.fixture
def nibo():
    return NiboFalso()


@pytest.fixture
def cli(banco, nibo):
    app = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"nibo": lambda: nibo, "paperless": lambda: None})
    return TestClient(app, client=("127.0.0.1", 50000))


def get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def test_so_boss_acessa(cli):
    assert get(cli, "/api/v1/cobrar/reembolsos", VIP).status_code == 403
    assert post(cli, "/api/v1/cobrar/lote/montar", None, VIP).status_code == 403


def test_reembolsos_lista_contratantes_e_o_lote_da_bekaa(cli):
    d = get(cli, "/api/v1/cobrar/reembolsos").json()["dados"]
    ness = next(e for e in d["empresas"] if e["empresa_id"] == "ness")
    assert ness["em_aberto"] == "150.00" and [i["descricao"] for i in ness["itens"]] == ["HOTEL", "TAXI"]
    assert all(i["comprovante"] == "faltando" for i in ness["itens"])
    assert "bekaa" not in {e["empresa_id"] for e in d["empresas"]}  # a Bekaa não gera cobrança
    assert d["lote"]["texto_confirmacao"] == "Lançar no Nibo da Bekaa: 1 despesas, R$ 70,00." and d["lote"]["id"] is None


def test_abrir_cobrar_e_receber_reembolso_avanca_o_estado(cli):
    rid = post(cli, "/api/v1/cobrar/reembolsos", {"empresa_id": "ness"}).json()["dados"]["id"]
    assert post(cli, f"/api/v1/cobrar/reembolsos/{rid}/cobrado").status_code == 200
    assert post(cli, f"/api/v1/cobrar/reembolsos/{rid}/cobrado").status_code == 409  # já cobrado
    ness = next(e for e in get(cli, "/api/v1/cobrar/reembolsos").json()["dados"]["empresas"] if e["empresa_id"] == "ness")
    assert [r["estado"] for r in ness["reembolsos"]] == ["cobrado"]


def test_bekaa_nao_abre_cobranca(cli):
    r = post(cli, "/api/v1/cobrar/reembolsos", {"empresa_id": "bekaa"})
    assert r.status_code == 400 and "lote" in r.json()["mensagem"]


def test_lote_confirmacao_divergente_409_e_nada_grava(cli, nibo):
    lote = post(cli, "/api/v1/cobrar/lote/montar").json()["dados"]
    r = post(cli, f"/api/v1/cobrar/lote/{lote['id']}/executar", {"confirmacao": "Lançar no Nibo da Bekaa: 1 despesas, R$ 70,01."})
    assert r.status_code == 409 and r.json()["erro"] == "confirmacao_divergente" and nibo.criacoes == 0


def test_lote_executa_com_o_texto_exato_e_nao_duplica(cli, nibo):
    lote = post(cli, "/api/v1/cobrar/lote/montar").json()["dados"]
    corpo = {"confirmacao": lote["texto_confirmacao"]}
    r = post(cli, f"/api/v1/cobrar/lote/{lote['id']}/executar", corpo)
    assert r.status_code == 200 and r.json()["dados"] == {"ok": 1, "erro": 0}
    post(cli, f"/api/v1/cobrar/lote/{lote['id']}/executar", corpo)
    assert nibo.criacoes == 1


def test_lote_sem_nibo_configurado_devolve_503(banco):
    app = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"nibo": lambda: None, "paperless": lambda: None})
    c = TestClient(app, client=("127.0.0.1", 50000))
    lote = post(c, "/api/v1/cobrar/lote/montar").json()["dados"]
    r = post(c, f"/api/v1/cobrar/lote/{lote['id']}/executar", {"confirmacao": lote["texto_confirmacao"]})
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def test_comprovantes_lista_candidatos_e_confirma_ou_rejeita(cli, banco):
    from gabi.cobrar.comprovantes import propor_vinculos, registrar_comprovante
    c = conectar(banco)
    cid = registrar_comprovante(c, paperless_id=77, tipo="comprovante_pix", valor_centavos=10000, data="2026-10-01")
    propor_vinculos(c, cid)
    c.close()
    d = get(cli, "/api/v1/cobrar/comprovantes").json()["dados"]
    assert len(d["candidatos"]) == 1 and d["candidatos"][0]["lancamento"]["descricao"] == "HOTEL" and d["candidatos"][0]["confianca"] >= 0.5
    assert [x["descricao"] for x in d["sem_comprovante"]] == ["HOTEL", "TAXI", "LICENCA"]  # a Bekaa também precisa (o lote anexa o comprovante)
    vid = d["candidatos"][0]["vinculo_id"]
    assert post(cli, f"/api/v1/cobrar/vinculos/{vid}/confirmar").status_code == 200
    assert post(cli, f"/api/v1/cobrar/vinculos/{vid}/rejeitar").status_code == 409  # já decidido
    d2 = get(cli, "/api/v1/cobrar/comprovantes").json()["dados"]
    assert d2["candidatos"] == [] and [x["descricao"] for x in d2["sem_comprovante"]] == ["TAXI", "LICENCA"]


def test_cobranca_cria_rascunho_e_enviar_e_403(cli):
    r = post(cli, "/api/v1/cobrar/cobrancas", {"empresa_id": "ness"})
    assert r.status_code == 201
    c = r.json()["dados"]
    assert c["para"] == "fin@ness.com.br" and c["total"] == "150.00" and c["itens"] == 2 and "Total: R$ 150,00" in c["corpo"]
    assert post(cli, f"/api/v1/cobrar/cobrancas/{c['id']}/enviar").status_code == 403
    assert post(cli, f"/api/v1/cobrar/cobrancas/{c['id']}/enviar").json()["erro"] == "nao_permitido"
    lista = get(cli, "/api/v1/cobrar/cobrancas?empresa_id=ness").json()["dados"]["itens"]
    assert [x["id"] for x in lista] == [c["id"]]


def test_pedidos_listar_decidir_aprova_e_entra_na_agenda(cli, banco):
    from gabi.cobrar.pedidos import registrar
    c = conectar(banco)
    pid = registrar(c, solicitante="whatsapp:+5511911110000", canal="whatsapp", mensagem_original="paga?", descricao="Dentista", valor="150,00",
                    vencimento="2026-10-20", anexo_base64=None, anexo_paperless_id=None, pix_chave="d@pix", linha_digitavel=None, para_quem=None).pedido_id
    c.close()
    pend = get(cli, "/api/v1/cobrar/pedidos").json()["dados"]["itens"]
    assert [p["id"] for p in pend] == [pid] and pend[0]["valor"] == "150.00" and pend[0]["solicitante"] == "Ana"
    assert post(cli, f"/api/v1/cobrar/pedidos/{pid}/decidir", {"acao": "aprovar", "beneficiario_id": "ana"}).status_code == 400  # falta a conta
    r = post(cli, f"/api/v1/cobrar/pedidos/{pid}/decidir", {"acao": "aprovar", "conta_id": 1, "beneficiario_id": "ana"})
    assert r.status_code == 200
    assert post(cli, f"/api/v1/cobrar/pedidos/{pid}/decidir", {"acao": "recusar"}).status_code == 409
    pagar = get(cli, "/api/v1/contas-pagar").json()["dados"]
    assert any(i["nome"] == "Dentista" for g in pagar.values() for i in g)  # entrou na agenda
    assert get(cli, "/api/v1/cobrar/pedidos").json()["dados"]["itens"] == []
    assert [p["estado"] for p in get(cli, "/api/v1/cobrar/pedidos?estado=decididos").json()["dados"]["itens"]] == ["aprovado"]
