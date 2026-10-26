import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.dinheiro.valor import para_centavos

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
AGORA = dt.datetime(2026, 10, 8, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))  # quinta-feira; semana começa em 2026-10-05
JSON = {"Content-Type": "application/json"}


def _l(c, conta, ext, data, desc, v, nat, cat=None, empresa=None, parcela=None, parcelas=None, fatura=None):
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, categoria_id, categoria_origem, "
              "empresa_id, empresa_origem, parcela, parcelas, fatura_id, status) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'posted')",
              (conta, ext, data, v, desc, desc.split()[0], nat, cat, "voce" if cat else None, empresa, "voce" if empresa else None, parcela, parcelas, fatura))


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 PJ','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado, limite_centavos, vencimento_fatura) values ('c1','Itau','CREDIT','Itaú Visa','sim',500000,'2026-10-20')")
    for n in ("Mercado", "Transporte", "Receita", "Assinaturas", "Casa"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    c.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f0','c1','2026-09-20',35590,'PAID',2)")
    c.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','c1','2026-10-20',47590,'OPEN',2)")
    # banco (caixa)
    _l(c, 1, "b-1", "2026-10-07", "PADARIA BOM PAO", -3550, "caixa+custo", 1)
    _l(c, 1, "b-2", "2026-10-06", "UBER TRIP", -2250, "caixa+custo", 2, empresa="e1")
    _l(c, 1, "b-3", "2026-10-05", "SALARIO EMPRESA", 800000, "caixa", 3)
    _l(c, 1, "b-4", "2026-09-28", "MERCADO CENTRAL", -10000, "caixa+custo", 1)
    # cartão (custo)
    for ext, d in (("n1", "2026-10-03"), ("n2", "2026-09-03"), ("n3", "2026-08-03"), ("n4", "2026-07-03")):
        _l(c, 2, ext, d, "NETFLIX", -5590, "custo", 4, fatura="f1" if ext == "n1" else None)
    for ext, d, par, fat in (("tv3", "2026-10-02", 3, "f1"), ("tv2", "2026-09-02", 2, None), ("tv1", "2026-08-02", 1, None)):
        _l(c, 2, ext, d, "TV PARCELADA", -30000, "custo", 5, parcela=par, parcelas=10, fatura=fat)
    _l(c, 2, "lj", "2026-10-04", "LOJA X", -12000, "custo", 1, fatura="f1")
    for em, v in (("2026-10-01T23:00:00", 1000000), ("2026-10-07T23:00:00", 1100000), ("2026-10-08T14:00:00", 1234560)):
        c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,?,?)", (em, v))
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (2,'2026-10-08T14:00:00', -47590)")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-08T17:00:00+00:00','2026-10-08T17:00:30+00:00','ok',1)")
    c.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def patch(cli, url, corpo, h=BOSS):
    return cli.patch(url, headers={**h, **JSON}, content=json.dumps(corpo))


@pytest.mark.parametrize("url", ["/api/v1/caixa/semanas", "/api/v1/destino", "/api/v1/cartoes", "/api/v1/parcelas", "/api/v1/assinaturas", "/api/v1/custo"])
def test_exigem_boss_e_trazem_envelope(cli, url):
    assert get(cli, url, VIP).status_code == 403 and cli.get(url).status_code == 401
    j = get(cli, url).json()
    assert {"dados_ate", "desatualizado", "fontes", "dados"} <= set(j)


# ---------------- semanas ----------------
def _semana(j, inicio):
    return next(s for s in j["dados"]["semanas"] if s["inicio"] == inicio)


def test_semanas_cobrem_passado_atual_e_futuro_a_partir_de_segunda(cli):
    j = get(cli, "/api/v1/caixa/semanas").json()
    inicios = [s["inicio"] for s in j["dados"]["semanas"]]
    assert inicios[0] == "2026-08-10" and "2026-10-05" in inicios and inicios[-1] == "2026-11-02" and len(inicios) == 13
    assert all(dt.date.fromisoformat(i).weekday() == 0 for i in inicios)


def test_semana_atual_entradas_saidas_por_categoria_e_saldo(cli):
    s = _semana(get(cli, "/api/v1/caixa/semanas").json(), "2026-10-05")
    assert s["entradas"] == [{"categoria": "Receita", "valor": "8000.00"}]
    assert {x["categoria"]: x["valor"] for x in s["saidas"]} == {"Mercado": "-35.50", "Transporte": "-22.50"}
    assert s["saldo"] == "12345.60" and s["projecao"] is False


def test_semana_passada_usa_o_saldo_do_fim_da_semana(cli):
    s = _semana(get(cli, "/api/v1/caixa/semanas").json(), "2026-09-28")
    assert {x["categoria"]: x["valor"] for x in s["saidas"]} == {"Mercado": "-100.00"} and s["saldo"] == "10000.00"


def test_semana_futura_e_projecao_e_traz_a_fatura(cli):
    j = get(cli, "/api/v1/caixa/semanas").json()
    s = _semana(j, "2026-10-19")
    assert s["projecao"] is True and {x["categoria"]: x["valor"] for x in s["saidas"]} == {"fatura": "-475.90"}
    assert s["saldo"] == "11869.70" and s["entradas"] == []


def test_semanas_cartao_nao_entra_no_caixa(cli):
    s = _semana(get(cli, "/api/v1/caixa/semanas").json(), "2026-10-05")
    assert "Assinaturas" not in {x["categoria"] for x in s["saidas"]}  # compra no cartão é custo, não caixa


# ---------------- destino ----------------
def test_destino_fluxos_origem_categoria_destino(cli):
    d = get(cli, "/api/v1/destino?periodo=mes").json()["dados"]
    f = {(x["de"], x["para"]): x["valor"] for x in d["fluxos"]}
    assert f[("C6 PJ", "Mercado")] == "35.50" and f[("Itaú Visa", "Mercado")] == "120.00" and f[("Itaú Visa", "Assinaturas")] == "55.90"
    assert f[("Mercado", "Consumo pessoal")] == "155.50" and f[("Transporte", "A receber: Ness")] == "22.50"
    assert d["total"] == "533.90"
    tipos = {n["nome"]: n["tipo"] for n in d["nos"]}
    assert tipos["C6 PJ"] == "origem" and tipos["Mercado"] == "categoria" and tipos["A receber: Ness"] == "destino"


def test_destino_compara_com_o_periodo_anterior(cli):
    c = get(cli, "/api/v1/destino?periodo=mes").json()["dados"]["comparacao"]
    assert c[0] == {"categoria": "Mercado", "atual": "155.50", "anterior": "0.00", "variacao": "155.50"}
    assert next(x for x in c if x["categoria"] == "Casa") == {"categoria": "Casa", "atual": "300.00", "anterior": "300.00", "variacao": "0.00"}


def test_destino_periodo_invalido_400(cli):
    assert get(cli, "/api/v1/destino?periodo=ontem").status_code == 400


# ---------------- cartões ----------------
def test_cartoes_fatura_aberta_limite_e_categorias(cli):
    c = get(cli, "/api/v1/cartoes").json()["dados"]["itens"]
    assert len(c) == 1 and c[0]["apelido"] == "Itaú Visa"
    fa = c[0]["fatura_aberta"]
    assert (fa["id"], fa["vencimento"], fa["total"], fa["status"], fa["percentual_limite"]) == ("f1", "2026-10-20", "475.90", "OPEN", 9.5)
    assert {x["categoria"]: x["valor"] for x in c[0]["por_categoria"]} == {"Assinaturas": "55.90", "Casa": "300.00", "Mercado": "120.00"}


def test_cartoes_serie_12_meses(cli):
    s = get(cli, "/api/v1/cartoes").json()["dados"]["itens"][0]["serie_12m"]
    assert len(s) == 12 and s[-1] == {"mes": "2026-10", "total": "475.90"}
    assert next(x for x in s if x["mes"] == "2026-09")["total"] == "355.90"


# ---------------- parcelas ----------------
def test_parcelas_comprometido_por_mes_e_andamento(cli):
    d = get(cli, "/api/v1/parcelas").json()["dados"]
    assert len(d["itens"]) == 1
    tv = d["itens"][0]
    assert (tv["descricao"], tv["parcela"], tv["parcelas"], tv["restante"], tv["valor_parcela"], tv["termina_em"], tv["termina_neste_mes"]) == (
        "TV PARCELADA", 3, 10, 7, "300.00", "2027-05", False)
    assert [m["mes"] for m in d["por_mes"]] == ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05"]
    assert all(m["total"] == "300.00" for m in d["por_mes"])


def test_parcelas_destaca_o_que_termina_neste_mes(cli, banco):
    c = conectar(banco)
    _l(c, 2, "ult", "2026-10-02", "GELADEIRA", -20000, "custo", 5, parcela=6, parcelas=6)
    c.close()
    itens = {i["descricao"]: i for i in get(cli, "/api/v1/parcelas").json()["dados"]["itens"]}
    assert itens["GELADEIRA"]["restante"] == 0 and itens["GELADEIRA"]["termina_neste_mes"] is True


# ---------------- assinaturas ----------------
def test_assinaturas_lista_com_total_e_status_inicial(cli):
    d = get(cli, "/api/v1/assinaturas").json()["dados"]
    assert d["total_mensal"] == "55.90" and len(d["itens"]) == 1
    n = d["itens"][0]
    assert (n["nome"], n["mensal"], n["anual"], n["status"], n["lembrar_ate_cancelar"]) == ("NETFLIX", "55.90", "670.80", "a_conferir", False)
    assert isinstance(n["id"], int) and n["sinais"] == {"nova": False, "reajustou": None, "cobrada_depois_de_cancelar": False}


def test_assinatura_traz_historico_de_12_meses_desde_e_ultimo(cli):
    n = get(cli, "/api/v1/assinaturas").json()["dados"]["itens"][0]
    assert [m["mes"] for m in n["serie_12m"]][-4:] == ["2026-07", "2026-08", "2026-09", "2026-10"] and len(n["serie_12m"]) == 12
    assert [m["total"] for m in n["serie_12m"]][-4:] == ["55.90"] * 4 and n["serie_12m"][0]["total"] == "0.00"
    assert (n["desde"], n["ultimo"], n["total_12m"]) == ("2026-07-03", "2026-10-03", "223.60")


def test_assinatura_patch_muda_status_e_registra_quando(cli, banco):
    aid = get(cli, "/api/v1/assinaturas").json()["dados"]["itens"][0]["id"]
    r = patch(cli, f"/api/v1/assinaturas/{aid}", {"status": "cancelar", "lembrar_ate_cancelar": True})
    assert r.status_code == 200 and r.json()["dados"]["status"] == "cancelar" and r.json()["dados"]["lembrar_ate_cancelar"] is True
    assert conectar(banco).execute("select status_em from assinatura").fetchone()[0] == "2026-10-08"


def test_assinatura_cobrada_depois_de_marcada_para_cancelar_e_alerta_forte(cli, banco):
    aid = get(cli, "/api/v1/assinaturas").json()["dados"]["itens"][0]["id"]
    patch(cli, f"/api/v1/assinaturas/{aid}", {"status": "cancelar"})
    c = conectar(banco)
    c.execute("update assinatura set status_em='2026-10-01'")  # marcada antes da cobrança de 03/10
    c.close()
    d = get(cli, "/api/v1/assinaturas").json()["dados"]
    assert d["itens"][0]["sinais"]["cobrada_depois_de_cancelar"] is True and d["alerta_forte"] is True


def test_assinatura_patch_invalido(cli):
    aid = get(cli, "/api/v1/assinaturas").json()["dados"]["itens"][0]["id"]
    assert patch(cli, f"/api/v1/assinaturas/{aid}", {"status": "talvez"}).status_code == 400
    assert patch(cli, f"/api/v1/assinaturas/{aid}", {"lembrar_ate_cancelar": "sim"}).status_code == 400
    assert patch(cli, f"/api/v1/assinaturas/{aid}", {}).status_code == 400
    assert patch(cli, "/api/v1/assinaturas/999", {"status": "manter"}).status_code == 404


# ---------------- custo do modelo ----------------
def test_custo_zero_sem_uso_e_soma_do_dia_e_do_mes(cli, banco):
    d = get(cli, "/api/v1/custo").json()["dados"]
    assert d["dia_usd"] == 0.0 and d["mes_usd"] == 0.0 and d["teto_dia_usd"] > 0 and d["alerta"] is None
    c = conectar(banco)
    c.execute("insert into custo_modelo(em, custo_usd, tarefa) values ('2026-10-08T10:00:00-03:00', 0.5, 'classificar')")
    c.execute("insert into custo_modelo(em, custo_usd, tarefa) values ('2026-10-02T10:00:00-03:00', 1.5, 'classificar')")
    c.execute("insert into custo_modelo(em, custo_usd, tarefa) values ('2026-09-30T10:00:00-03:00', 9.0, 'classificar')")
    c.close()
    d = get(cli, "/api/v1/custo").json()["dados"]
    assert d["dia_usd"] == 0.5 and d["mes_usd"] == 2.0  # setembro não entra no mês de outubro


# ---------------- lacunas achadas por mutação ----------------
def test_semana_atual_ignora_lancamento_com_data_futura(cli, banco):
    c = conectar(banco)
    _l(c, 1, "fut", "2026-10-10", "COISA FUTURA", -999900, "caixa+custo", 1)  # depois de hoje (08/10), mas ainda na semana
    c.close()
    s = _semana(get(cli, "/api/v1/caixa/semanas").json(), "2026-10-05")
    assert {x["categoria"]: x["valor"] for x in s["saidas"]} == {"Mercado": "-35.50", "Transporte": "-22.50"}


def test_parcelas_nao_inclui_meses_que_ja_passaram(cli, banco):
    c = conectar(banco)
    _l(c, 2, "velha", "2026-06-02", "SOFA PARADO", -10000, "custo", 5, parcela=2, parcelas=10)  # última parcela lida em junho
    c.close()
    d = get(cli, "/api/v1/parcelas").json()["dados"]
    assert min(m["mes"] for m in d["por_mes"]) > "2026-10"


def test_cartao_com_todas_as_faturas_pagas_nao_tem_fatura_aberta(cli, banco):
    c = conectar(banco)
    c.execute("update fatura set pagamento_status='PAID'")
    c.close()
    it = get(cli, "/api/v1/cartoes").json()["dados"]["itens"][0]
    assert it["fatura_aberta"] is None and it["por_categoria"] == []


def test_cartao_fatura_nao_confirmada_com_debito_no_banco_nao_e_aberta(cli, banco):
    """Mesma regra do Caixa: o banco diz UNCONFIRMED mas o débito igual já saiu da conta BANK."""
    c = conectar(banco)
    c.execute("update fatura set pagamento_status='PAST_DUE_UNCONFIRMED', vencimento='2026-10-07' where id='f1'")
    _l(c, 1, "pg1", "2026-10-07", "PGTO FATURA", -47590, "custo", 1)
    c.close()
    it = get(cli, "/api/v1/cartoes").json()["dados"]["itens"][0]
    assert it["fatura_aberta"] is None and it["por_categoria"] == []


def test_cartao_fatura_nao_confirmada_sem_debito_segue_aberta(cli, banco):
    c = conectar(banco)
    c.execute("update fatura set pagamento_status='PAST_DUE_UNCONFIRMED', vencimento='2026-10-07' where id='f1'")
    c.close()
    assert get(cli, "/api/v1/cartoes").json()["dados"]["itens"][0]["fatura_aberta"]["status"] == "PAST_DUE_UNCONFIRMED"


def test_entrada_recorrente_no_cartao_nao_e_assinatura(cli, banco):
    c = conectar(banco)
    for i, d in enumerate(("2026-10-05", "2026-09-05", "2026-08-05", "2026-07-05")):
        _l(c, 2, f"cb{i}", d, "CASHBACK LOJA", 500, "custo", 4)  # +R$ 5,00 por mês: entrada, não assinatura
    c.close()
    nomes = [i["nome"] for i in get(cli, "/api/v1/assinaturas").json()["dados"]["itens"]]
    assert nomes == ["NETFLIX"]


def test_cancelamento_marcado_depois_da_ultima_cobranca_nao_dispara_alerta(cli, banco):
    aid = get(cli, "/api/v1/assinaturas").json()["dados"]["itens"][0]["id"]
    patch(cli, f"/api/v1/assinaturas/{aid}", {"status": "cancelar"})
    c = conectar(banco)
    c.execute("update assinatura set status_em='2026-10-05'")  # a última cobrança foi em 03/10, antes de marcar
    c.close()
    d = get(cli, "/api/v1/assinaturas").json()["dados"]
    assert d["itens"][0]["sinais"]["cobrada_depois_de_cancelar"] is False and d["alerta_forte"] is False


# ---------------- destino agrupado (abas Fornecedores / Por pessoa) ----------------
def test_destino_agrupado_por_fornecedor_e_pessoa(cli):
    j = get(cli, "/api/v1/destino/agrupado?periodo=mes&por=fornecedor").json()
    assert {"dados_ate", "fontes"} <= set(j)
    d = j["dados"]
    assert d["por"] == "fornecedor" and d["total"] == "533.90"
    assert d["itens"][0]["nome"] == "TV" and d["itens"][0]["valor"] == "300.00"
    assert {"nome", "valor", "pct", "variacao"} <= set(d["itens"][0])
    p = get(cli, "/api/v1/destino/agrupado?periodo=mes&por=pessoa").json()["dados"]
    assert p["itens"][0]["nome"] == "(sem pessoa)"
    g = get(cli, "/api/v1/destino/agrupado?periodo=mes&por=gastador").json()["dados"]
    assert g["por"] == "gastador" and g["total"] == "533.90" and g["itens"][0]["nome"] == "(a indicar)"


def test_destino_agrupado_valida_entrada_e_exige_boss(cli):
    assert get(cli, "/api/v1/destino/agrupado?por=xis").status_code == 400
    assert get(cli, "/api/v1/destino/agrupado?periodo=ano").status_code == 400
    assert get(cli, "/api/v1/destino/agrupado", VIP).status_code == 403


def _custo(cli):
    return cli.get("/api/v1/custo", headers=BOSS).json()["dados"]


def test_custo_sem_cambio_nao_inventa_brl(cli):
    assert _custo(cli)["cambio_usd_brl"] is None


def test_custo_com_cambio_do_parametro_devolve_o_cambio(cli, banco):
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('cambio_usd_brl', ?)", (json.dumps(5.5),))
    c.close()
    assert _custo(cli)["cambio_usd_brl"] == "5.50"


def test_assinaturas_incluem_as_da_categoria_que_o_detector_nao_acha_e_marcam_as_que_pararam(cli, banco):
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('categorias_assinatura', ?)", (json.dumps(["Assinaturas"]),))
    for i, mes in enumerate(("2026-02", "2026-03", "2026-04")):   # parou de cobrar em abril: o detector (últimos 4 meses) não vê
        _l(c, 1, f"old{i}", f"{mes}-10", "OLDSAAS PRO", -9900, "custo", 4)
    c.close()
    d = get(cli, "/api/v1/assinaturas").json()["dados"]
    por_nome = {i["nome"]: i for i in d["itens"]}
    assert por_nome["OLDSAAS"]["ativa"] is False and por_nome["OLDSAAS"]["status"] == "a_conferir"
    assert por_nome["NETFLIX"]["ativa"] is True
    assert [i["nome"] for i in d["itens"]].index("NETFLIX") < [i["nome"] for i in d["itens"]].index("OLDSAAS")  # ativas primeiro
    assert d["total_mensal"] == "55.90"   # só as ativas somam no mensal


def test_assinaturas_tiram_da_lista_o_habito_de_consumo_pelo_parametro(cli, banco):
    c = conectar(banco)
    for i, mes in enumerate(("2026-07", "2026-08", "2026-09", "2026-10")):
        _l(c, 1, f"alm{i}", f"{mes}-03", "AMORA", -5590, "custo", 1)   # categoria 1 = Mercado, mensal e igual: o detector acha
    c.close()
    assert "AMORA" in [i["nome"] for i in get(cli, "/api/v1/assinaturas").json()["dados"]["itens"]]
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('categorias_habito', ?)", (json.dumps(["Mercado"]),))
    c.close()
    nomes = [i["nome"] for i in get(cli, "/api/v1/assinaturas").json()["dados"]["itens"]]
    assert "AMORA" not in nomes and "NETFLIX" in nomes


def test_nao_e_assinatura_sai_do_total_e_dos_alertas_e_volta_ao_desfazer(cli, banco):
    d = get(cli, "/api/v1/assinaturas").json()["dados"]
    a = d["itens"][0]
    assert a["no_rol"] is True and d["total_mensal"] != "0.00"
    patch(cli, f"/api/v1/assinaturas/{a['id']}", {"status": "nao_assinatura"})
    d2 = get(cli, "/api/v1/assinaturas").json()["dados"]
    fora = next(i for i in d2["itens"] if i["id"] == a["id"])
    assert fora["no_rol"] is False  # continua na resposta, para o filtro "fora do rol" e o desfazer
    assert para_centavos(d2["total_mensal"]) == para_centavos(d["total_mensal"]) - para_centavos(a["mensal"])
    patch(cli, f"/api/v1/assinaturas/{a['id']}", {"status": "manter"})
    assert get(cli, "/api/v1/assinaturas").json()["dados"]["total_mensal"] == d["total_mensal"]

