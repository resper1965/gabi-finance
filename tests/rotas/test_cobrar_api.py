import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar

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
    return object()  # o lote do Nibo saiu (ADR-023): a fonte só precisa existir


@pytest.fixture
def cli(banco, nibo):
    app = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"nibo": lambda: nibo, "paperless": lambda: None})
    return TestClient(app, client=("127.0.0.1", 50000))


def get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def test_so_boss_acessa(cli):
    assert get(cli, "/api/v1/cobrar/notas", VIP).status_code == 403
    assert get(cli, "/api/v1/cobrar/a-receber", VIP).status_code == 403


def _nota(banco, tomador, venc, liquido, status="autorizada", pago=0):
    c = conectar(banco)
    n = c.execute("select count(*) from nota_fiscal").fetchone()[0] + 1
    c.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, tomador_doc, vencimento, valor_liquido_centavos, nibo_pago, importado_em, atualizado_em) "
              "values (?,?,?,?,?,?,?,?,?,?,'x','x')", (f"n{n}", str(n), venc, status, liquido + 10000, tomador, tomador, venc, liquido, pago))
    c.close()


def test_previsao_de_caixa_formata_valores_e_so_o_boss_ve(banco):
    _nota(banco, "IONIC", "2026-10-25", 2226122)
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    r = cli.get("/api/v1/cobrar/previsao?meses=2", headers=BOSS)
    assert r.status_code == 200
    d = r.json()["dados"]
    outubro = next(m for m in d["meses"] if m["mes"] == "2026-10")
    assert outubro["a_vencer"]["qtd"] == 1 and outubro["a_vencer"]["liquido"] == "22261.22" and outubro["a_vencer"]["bruto"] == "22361.22"
    assert "Nibo defasado" in d["aviso"] and len(d["meses"]) == 2
    assert cli.get("/api/v1/cobrar/previsao", headers=VIP).status_code == 403
    assert cli.get("/api/v1/cobrar/previsao?meses=0", headers=BOSS).status_code == 400


def test_notas_lista_so_autorizadas_em_aberto_e_formata_valores(banco):
    _nota(banco, "IONIC", "2026-10-25", 2226122)                 # a vencer
    _nota(banco, "BARRA", "2026-09-20", 366015)                  # vencida há 19 dias: a confirmar pelo extrato
    _nota(banco, "ANTIGA", "2026-05-10", 100000)                 # vencida há mais de 60 dias: provável baixa que faltou no Nibo
    _nota(banco, "PAGA", "2026-10-30", 50000, pago=1)           # o Nibo diz pago: aparece, mas não conta como a receber
    _nota(banco, "CANC", "2026-10-26", 9999, status="cancelada")
    _nota(banco, "NEG", "2026-10-27", 9999, status="negada")
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    r = cli.get("/api/v1/cobrar/notas", headers=BOSS)
    assert r.status_code == 200
    d = r.json()["dados"]
    por = {i["tomador"]: i for i in d["itens"]}
    assert set(por) == {"IONIC", "BARRA", "ANTIGA", "PAGA"}                               # cancelada e negada não entram
    assert (por["IONIC"]["liquido"], por["IONIC"]["bruto"], por["IONIC"]["situacao"]) == ("22261.22", "22361.22", "a_vencer")
    assert (por["BARRA"]["situacao"], por["ANTIGA"]["situacao"], por["PAGA"]["situacao"]) == ("a_confirmar", "antiga", "nibo_diz_pago")
    assert d["totais"] == {"a_vencer": "22261.22", "a_confirmar": "3660.15", "antigas": "1000.00", "nibo_diz_pago": "500.00", "recebidas": "0.00"}
    assert [i["tomador"] for i in d["itens"]][0] == "PAGA"                                   # vencimento mais distante primeiro
    assert [i["tomador"] for i in cli.get("/api/v1/cobrar/notas?aberta=1", headers=BOSS).json()["dados"]["itens"]] == ["IONIC", "BARRA", "ANTIGA"]
    assert cli.get("/api/v1/cobrar/notas", headers=VIP).status_code == 403


def test_recebimentos_propostos_sao_listados_e_confirmar_marca_a_nota_como_recebida(banco):
    _nota(banco, "BARRA", "2026-10-15", 366015)
    c = conectar(banco)
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (2,'cred1','2026-10-16',366015,'Pix recebido BARRA','posted')")
    from gabi.cobrar.recebimentos import propor_recebimentos
    assert propor_recebimentos(c) == 1
    c.close()
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    r = cli.get("/api/v1/cobrar/recebimentos", headers=BOSS)
    assert r.status_code == 200
    it = r.json()["dados"]["itens"][0]
    assert it["nota"]["tomador"] == "BARRA" and it["nota"]["liquido"] == "3660.15" and it["lancamento"]["valor"] == "3660.15" and it["confianca"] >= 0.8 and "valor igual" in it["motivo"]
    ok = cli.post(f"/api/v1/cobrar/recebimentos/{it['id']}/confirmar", headers={**BOSS, **JSON}, content="{}")
    assert ok.status_code == 200
    assert cli.post(f"/api/v1/cobrar/recebimentos/{it['id']}/confirmar", headers={**BOSS, **JSON}, content="{}").status_code == 409     # já decidido
    notas = cli.get("/api/v1/cobrar/notas", headers=BOSS).json()["dados"]
    assert notas["itens"][0]["situacao"] == "recebida" and notas["totais"]["recebidas"] == "3660.15" and notas["totais"]["a_vencer"] == "0.00"
    assert cli.get("/api/v1/cobrar/recebimentos", headers=BOSS).json()["dados"]["itens"] == []
    assert cli.post(f"/api/v1/cobrar/recebimentos/{it['id']}/confirmar", headers={**VIP, **JSON}, content="{}").status_code == 403


def test_rejeitar_recebimento_e_idempotente_a_404_para_inexistente(banco):
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    assert cli.post("/api/v1/cobrar/recebimentos/999/rejeitar", headers={**BOSS, **JSON}, content="{}").status_code == 404


def test_a_receber_do_mes_separa_recebido_atrasado_e_a_receber(banco):
    c = conectar(banco)
    for m in (5, 6, 7, 8, 9):      # pagador regular no C6 PJ (conta 2): vem dia 7; em outubro já veio
        c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza) values (2,?,?,1000000,'Pix recebido de CLIENTE X LTDA','caixa')", (f"r{m}", f"2026-{m:02d}-07"))
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza) values (2,'r10','2026-10-07',1000000,'Pix recebido de CLIENTE X LTDA','caixa')")
    c.close()
    _nota(banco, "IONIC", "2026-10-25", 2226122)       # a receber
    _nota(banco, "BARRA", "2026-10-03", 366015)        # venceu e não foi confirmada: atrasada
    _nota(banco, "PAGA", "2026-10-30", 50000, pago=1)  # Nibo diz pago: conferir, não é recebimento
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    r = cli.get("/api/v1/cobrar/a-receber", headers=BOSS)
    assert r.status_code == 200
    d = r.json()["dados"]
    [rec] = d["recorrentes"]
    assert rec["situacao"] == "recebido" and rec["recebido_em"] == "2026-10-07" and rec["recebido"] == "10000.00"
    sit = {n["pagador"]: n["situacao"] for n in d["notas"]}
    assert sit == {"IONIC": "a_receber", "BARRA": "atrasado", "PAGA": "nibo_diz_pago"}
    assert d["totais"]["notas"]["falta"] == "26421.37" and d["totais"]["notas"]["atrasado"] == "3660.15" and d["totais"]["recorrentes"]["recebido"] == "10000.00"
    assert rec["extrato"]["conta"] == "C6 PJ" and "CLIENTE X" in rec["extrato"]["descricao"]
    assert cli.get("/api/v1/cobrar/a-receber", headers=VIP).status_code == 403


def test_a_receber_nota_com_credito_proposto_vira_credito_provavel_com_o_lancamento(banco):
    _nota(banco, "BARRA", "2026-10-03", 366015)
    c = conectar(banco)
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (2,'x1','2026-10-05',366015,'Pix recebido BARRA DO PARA','posted')")
    c.execute("insert into recebimento_nota(nota_id, lancamento_id, confianca, motivo, criado_em) select id, (select max(id) from lancamento), 0.9, 'valor igual', 'x' from nota_fiscal")
    c.close()
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    [n] = cli.get("/api/v1/cobrar/a-receber", headers=BOSS).json()["dados"]["notas"]
    assert n["situacao"] == "credito_provavel" and n["recebido_em"] == "2026-10-05" and n["extrato"]["descricao"] == "Pix recebido BARRA DO PARA"


def test_a_receber_manuais_em_string_e_cancelar_confirmar(banco):
    from gabi.cobrar.receber_manual import propor, registrar
    c = conectar(banco)
    a = registrar(c, pagador="ORM Reis", valor="1500,00", vencimento="2026-10-20", quem="r", origem="hermes", agora=AGORA)["id"]
    b = registrar(c, pagador="Outro Cliente", valor="-300,00", quem="r", origem="hermes", agora=AGORA)["id"]
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (2,'m1','2026-10-05',150000,'Pix ORM REIS LTDA','posted')")
    assert propor(c) == 1
    pid = c.execute("select id from receber_manual_proposta").fetchone()[0]
    c.close()
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))
    d = cli.get("/api/v1/cobrar/a-receber", headers=BOSS).json()["dados"]
    por = {i["pagador"]: i for i in d["manuais"]}
    assert por["ORM Reis"]["esperado"] == "1500.00" and por["ORM Reis"]["situacao"] == "credito_provavel" and por["ORM Reis"]["proposta"]["valor"] == "1500.00"
    assert por["Outro Cliente"]["esperado"] == "-300.00" and por["Outro Cliente"]["recebido"] is None
    assert d["totais"]["manuais"]["esperado"] == "1200.00" and d["totais"]["manuais"]["recebido"] == "0.00"
    base = "/api/v1/cobrar/a-receber-manual"
    assert post(cli, f"{base}/propostas/{pid}/confirmar", h=VIP).status_code == 403
    assert post(cli, f"{base}/propostas/{pid}/confirmar").status_code == 200
    assert post(cli, f"{base}/propostas/{pid}/confirmar").status_code == 409
    assert post(cli, f"{base}/propostas/999/rejeitar").status_code == 404
    assert post(cli, f"{base}/{a}/cancelar").status_code == 409       # já recebido
    assert post(cli, f"{base}/999/cancelar").status_code == 404
    assert post(cli, f"{base}/{b}/cancelar").status_code == 200
    assert post(cli, f"{base}/{b}/cancelar").status_code == 409
    d = cli.get("/api/v1/cobrar/a-receber", headers=BOSS).json()["dados"]
    assert [i["situacao"] for i in d["manuais"]] == ["recebido"] and d["totais"]["manuais"]["recebido"] == "1500.00"
