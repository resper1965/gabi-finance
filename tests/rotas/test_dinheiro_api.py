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
AGORA = dt.datetime(2026, 10, 8, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
JSON = {"Content-Type": "application/json"}


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 PJ','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Itau','BANK','Itaú PF','a_decidir')")
    for n in ("Mercado", "Transporte"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into pessoa(id, nome) values ('p1','Ricardo')")
    c.execute("insert into pessoa(id, nome) values ('p9','Ana')")
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    for i, (d, desc, v) in enumerate([("2026-10-07", "PADARIA BOM PAO", -3550), ("2026-10-06", "UBER TRIP", -2250), ("2026-10-05", "SALARIO", 800000),
                                       ("2026-10-04", "UBER TRIP", -3100), ("2026-09-20", "MERCADO", -31000)], start=1):
        c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, status) "
                  "values (1,?,?,?,?,?,?, 'posted')", (f"l{i}", d, v, desc, desc.split()[0], "caixa+custo" if v < 0 else "caixa"))
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,'2026-10-07T23:00:00', 1000000)")
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,'2026-10-08T14:00:00', 1234560)")
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (2,'2026-10-08T14:00:00', 999)")
    for cid, nome, vu, est, v in [("iptu:2026-10", "IPTU", "2026-10-01", "atrasado", 50000), ("cond:2026-10", "Condomínio", "2026-10-08", "aberto", 80000),
                                  ("luz:2026-10", "Luz", "2026-10-12", "aberto", 23050), ("escola:2026-10", "Escola", "2026-11-20", "previsto", 300000),
                                  ("mens:2026-10", "Mensalidade", "2026-10-07", "a_conferir", 150000)]:
        c.execute("insert into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, forma, estado, dados) "
                  "values (?, 'planilha', ?, ?, ?, ?, ?, 'padrao', 'boleto', ?, '{}')", (cid, cid.split(':')[0], nome, vu, vu, v, est))
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-08T17:00:00+00:00','2026-10-08T17:00:30+00:00','ok',1)")
    for f in ('notas-nibo', 'comprovantes-paperless'):  # fontes esperadas do envelope
        c.execute("insert into rodada(fonte, inicio, fim, status) values (?,'2026-10-08T17:00:00+00:00','2026-10-08T17:00:30+00:00','ok')", (f,))
    c.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def get(cli, url, h=BOSS):
    return cli.get(url, headers=h)


def patch(cli, url, corpo, h=BOSS):
    return cli.patch(url, headers={**h, **JSON}, content=json.dumps(corpo))


def post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo) if corpo is not None else None)


# ---------------- escopo e envelope ----------------
@pytest.mark.parametrize("url", ["/api/v1/caixa/resumo", "/api/v1/contas-pagar", "/api/v1/lancamentos", "/api/v1/sugestoes", "/api/v1/regras",
                                 "/api/v1/fontes", "/api/v1/rodadas"])
def test_rotas_de_dinheiro_exigem_boss(cli, url):
    assert get(cli, url, VIP).status_code == 403 and cli.get(url).status_code == 401


def test_toda_leitura_traz_o_envelope(cli):
    for url in ("/api/v1/caixa/resumo", "/api/v1/contas-pagar", "/api/v1/lancamentos", "/api/v1/sugestoes", "/api/v1/regras"):
        j = get(cli, url).json()
        assert {"dados_ate", "desatualizado", "fontes", "dados"} <= set(j), url
    assert get(cli, "/api/v1/caixa/resumo").json()["dados_ate"] == "2026-10-08T17:00:30Z"


# ---------------- caixa ----------------
def test_resumo_saldo_so_das_contas_liberadas_e_dinheiro_como_string(cli):
    d = get(cli, "/api/v1/caixa/resumo").json()["dados"]
    assert d["kpis"]["saldo"] == "12345.60"  # só a conta C6 PJ (liberada); a 'a_decidir' não entra
    assert isinstance(d["kpis"]["saldo"], str)
    assert d["kpis"]["a_pagar_7_dias"] == "1530.50"  # atrasada (500) + hoje (800) + 12/10 (230,50); "a conferir" e "previsto" fora


def test_resumo_traz_o_detalhe_que_o_painel_mostra_sob_cada_kpi(cli):
    d = get(cli, "/api/v1/caixa/resumo").json()["dados"]["detalhe"]
    assert d["saldo_por_conta"] == [{"apelido": "C6 PJ", "saldo": "12345.60"}]
    assert (d["a_pagar_contas"], d["a_pagar_vencidas"]) == (3, 1)
    assert d["cartoes_abertos"] == 0 and d["proxima_fatura"] is None
    assert {"assinaturas_ativas", "assinaturas_a_conferir"} <= set(d)


def test_resumo_serie_de_saldo_tem_passado_e_projecao(cli):
    s = get(cli, "/api/v1/caixa/resumo").json()["dados"]["serie_saldo"]
    assert s and all({"data", "valor", "projecao"} <= set(p) for p in s)
    assert any(p["projecao"] is False for p in s)
    assert [p["data"] for p in s] == sorted(p["data"] for p in s)


def test_resumo_atencao_aponta_o_que_precisa_de_voce(cli):
    a = {x["tipo"]: x for x in get(cli, "/api/v1/caixa/resumo").json()["dados"]["atencao"]}
    assert a["atrasadas"]["quantidade"] == 1 and a["a_conferir"]["quantidade"] == 1 and a["contas_a_decidir"]["quantidade"] == 1


def test_resumo_filtra_por_conta(cli):
    d = get(cli, "/api/v1/caixa/resumo?conta=Ita%C3%BA%20PF").json()["dados"]
    assert d["kpis"]["saldo"] == "0.00" or d["kpis"]["saldo"] == "9.99"


# ---------------- contas a pagar ----------------
def test_contas_a_pagar_agrupa_e_formata(cli):
    d = get(cli, "/api/v1/contas-pagar").json()["dados"]
    assert [i["id"] for i in d["atrasadas"]] == ["iptu:2026-10"] and d["atrasadas"][0]["dias_atraso"] == 7
    assert d["atrasadas"][0]["valor"] == "500.00" and [i["id"] for i in d["hoje"]] == ["cond:2026-10"]
    assert [i["id"] for i in d["a_conferir"]] == ["mens:2026-10"]


def test_marcar_paga_manual_pela_api(cli, banco):
    c = conectar(banco)
    c.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('iptu','IPTU','IPTU','dia:1')")
    c.close()
    r = post(cli, "/api/v1/contas-pagar/iptu:2026-10/paga")
    assert r.status_code == 200 and r.json()["id"] == "iptu:2026-10"
    assert conectar(banco).execute("select count(*) from valor_do_mes where tipo='pago'").fetchone()[0] == 1


def test_marcar_paga_de_id_inexistente_404(cli):
    r = post(cli, "/api/v1/contas-pagar/nada:2026-10/paga")
    assert r.status_code == 404 and r.json()["erro"] == "nao_encontrado"


# ---------------- lançamentos ----------------
def test_lancamentos_lista_paginada_com_origens(cli):
    j = get(cli, "/api/v1/lancamentos?limite=2").json()["dados"]
    assert len(j["itens"]) == 2 and j["total"] == 5 and j["limite"] == 2 and j["offset"] == 0
    x = j["itens"][0]
    assert {"id", "data", "estabelecimento", "valor", "categoria", "para_quem", "empresa", "conta"} <= set(x)
    assert x["valor"] == "-35.50" and x["categoria"] == {"id": None, "nome": None, "origem": None}


def test_lancamentos_filtros(cli):
    u = lambda q: get(cli, f"/api/v1/lancamentos?{q}").json()["dados"]
    assert u("texto=uber")["total"] == 2 and u("de=2026-10-06")["total"] == 2 and u("ate=2026-09-30")["total"] == 1
    assert u("pendente=para_quem")["total"] == 5 and u("conta=C6%20PJ")["total"] == 5


def test_lancamentos_limite_maximo_e_invalido(cli):
    assert get(cli, "/api/v1/lancamentos?limite=999").json()["dados"]["limite"] == 200
    assert get(cli, "/api/v1/lancamentos?limite=abc").status_code == 422 or get(cli, "/api/v1/lancamentos?limite=abc").status_code == 400


def test_patch_lancamento_muda_origem_para_voce(cli, banco):
    r = patch(cli, "/api/v1/lancamentos/1", {"categoria_id": 1, "beneficiario_id": "p9", "empresa_id": "e1"})
    assert r.status_code == 200
    x = r.json()["dados"]
    assert x["categoria"] == {"id": 1, "nome": "Mercado", "origem": "voce"} and x["para_quem"]["origem"] == "voce" and x["empresa"]["origem"] == "voce"


def test_patch_valor_inexistente_400_e_nada_muda(cli, banco):
    r = patch(cli, "/api/v1/lancamentos/1", {"categoria_id": 999})
    assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida"
    assert conectar(banco).execute("select categoria_id from lancamento where id=1").fetchone()[0] is None


def test_patch_null_limpa_o_campo(cli, banco):
    patch(cli, "/api/v1/lancamentos/1", {"categoria_id": 1})
    r = patch(cli, "/api/v1/lancamentos/1", {"categoria_id": None})
    assert r.json()["dados"]["categoria"]["id"] is None and r.json()["dados"]["categoria"]["origem"] is None


def test_patch_lancamento_inexistente_404_e_corpo_vazio_400(cli):
    assert patch(cli, "/api/v1/lancamentos/999", {"categoria_id": 1}).status_code == 404
    assert patch(cli, "/api/v1/lancamentos/1", {}).status_code == 400
    assert patch(cli, "/api/v1/lancamentos/1", {"valor_centavos": 1}).status_code == 400  # campo que não se edita


def test_lote_atualiza_varios_e_e_atomico(cli, banco):
    r = post(cli, "/api/v1/lancamentos/lote", {"ids": [2, 4], "mudancas": {"categoria_id": 2}, "criar_regra": False})
    assert r.status_code == 200 and r.json()["dados"]["atualizados"] == 2
    ruim = post(cli, "/api/v1/lancamentos/lote", {"ids": [1, 999], "mudancas": {"categoria_id": 1}, "criar_regra": False})
    assert ruim.status_code == 404
    assert conectar(banco).execute("select categoria_id from lancamento where id=1").fetchone()[0] is None  # nada mudou


def test_lote_sem_ids_ou_sem_mudancas_400(cli):
    assert post(cli, "/api/v1/lancamentos/lote", {"ids": [], "mudancas": {"categoria_id": 1}}).status_code == 400
    assert post(cli, "/api/v1/lancamentos/lote", {"ids": [1], "mudancas": {}}).status_code == 400


def test_lote_com_criar_regra_cria_regra_ativa_por_estabelecimento(cli, banco):
    r = post(cli, "/api/v1/lancamentos/lote", {"ids": [2, 4], "mudancas": {"categoria_id": 2, "beneficiario_id": "p9"}, "criar_regra": True})
    assert len(r.json()["dados"]["regras"]) == 1  # os dois são UBER: uma regra só
    c = conectar(banco)
    assert c.execute("select ativa from regra").fetchone()[0] == 1


# ---------------- sugestões e regras ----------------
def _sug(banco):
    from gabi.dinheiro.regras import criar_sugestao
    c = conectar(banco)
    sid = criar_sugestao(c, "regra", None, {"padrao": "UBER", "acao": {"categoria_id": 2}}, "Gabi sugere")
    c.close()
    return sid


def test_sugestoes_lista_pendentes_com_impacto(cli, banco):
    _sug(banco)
    s = get(cli, "/api/v1/sugestoes").json()["dados"]["itens"]
    assert len(s) == 1 and s[0]["tipo"] == "regra" and s[0]["estado"] == "pendente"
    assert s[0]["impacto"] == {"passado": 2, "futuro_estimado": 0.3}  # 2 lançamentos em 6 meses = 0,3 por mês


def test_aprovar_sugestao_cria_regra_e_aplica(cli, banco):
    sid = _sug(banco)
    r = post(cli, f"/api/v1/sugestoes/{sid}/aprovar", {})
    assert r.status_code == 200 and r.json()["dados"]["regra_id"] == 1
    c = conectar(banco)
    assert c.execute("select count(*) from lancamento where categoria_id=2 and categoria_origem='regra'").fetchone()[0] == 2


def test_aprovar_com_edicao(cli, banco):
    sid = _sug(banco)
    r = post(cli, f"/api/v1/sugestoes/{sid}/aprovar", {"edicao": {"acao": {"categoria_id": 1}}})
    assert r.status_code == 200
    assert json.loads(conectar(banco).execute("select acao from regra").fetchone()[0]) == {"categoria_id": 1}


def test_rejeitar_e_decidir_de_novo_409(cli, banco):
    sid = _sug(banco)
    assert post(cli, f"/api/v1/sugestoes/{sid}/rejeitar").status_code == 200
    r = post(cli, f"/api/v1/sugestoes/{sid}/aprovar", {})
    assert r.status_code == 409 and r.json()["erro"] == "conflito"
    assert post(cli, "/api/v1/sugestoes/999/aprovar", {}).status_code == 404


def test_regras_lista_e_liga_desliga(cli, banco):
    c = conectar(banco)
    c.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('UBER', '{\"categoria_id\": 2}', 0, '2026-10-08', 'gabi')")
    c.close()
    r = get(cli, "/api/v1/regras").json()["dados"]["itens"]
    assert r[0]["ativa"] is False and r[0]["acao"] == {"categoria_id": 2}
    assert r[0]["casam"] == 2  # lançamentos que o padrão pega (a Gabi mostra "N lançamentos" ao lado da regra)
    assert patch(cli, "/api/v1/regras/1", {"ativa": True}).status_code == 200
    assert conectar(banco).execute("select count(*) from lancamento where categoria_id=2").fetchone()[0] == 2  # ligar aplica ao passado
    assert patch(cli, "/api/v1/regras/1", {"ativa": "sim"}).status_code == 400
    assert patch(cli, "/api/v1/regras/999", {"ativa": True}).status_code == 404


# ---------------- fontes e rodadas ----------------
def test_fontes_e_rodadas(cli):
    f = get(cli, "/api/v1/fontes").json()["dados"]
    est = {x["nome"]: x["estado"] for x in f["fontes"]}
    assert est == {"open-finance": "ok", "notas-nibo": "ok", "comprovantes-paperless": "ok"}
    r = get(cli, "/api/v1/rodadas").json()["dados"]["itens"]
    of = [x for x in r if x["fonte"] == "open-finance"][0]
    assert of["status"] == "ok" and of["conferida"] is True


# ---------------- auditoria e segurança ----------------
def test_toda_chamada_v1_e_registrada(cli, banco):
    get(cli, "/api/v1/regras")
    get(cli, "/api/v1/regras", VIP)
    caminhos = [(r["caminho"], r["status"]) for r in conectar(banco).execute("select caminho, status from chamada order by id")]
    assert ("/api/v1/regras", 200) in caminhos and ("/api/v1/regras", 403) in caminhos


def test_post_v1_cross_site_recusado(cli, banco):
    r = cli.post("/api/v1/contas-pagar/iptu:2026-10/paga", headers={**BOSS, **JSON, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_rodada_traz_as_conferencias_reprovadas_so_de_contas_liberadas(cli, banco):
    c = conectar(banco)
    rid = c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-08T18:00:00+00:00','2026-10-08T18:10:00+00:00','ok',0)").lastrowid
    for conta, ok in ((1, 0), (2, 0)):  # conta 1 liberada (sim), conta 2 a_decidir
        c.execute("insert into conferencia(rodada_id, tipo, conta_id, ok, detalhe, criado_em) values (?,?,?,?,?, '2026-10-08T18:10:00+00:00')",
                  (rid, "dias_sem_buraco", conta, ok, "dias úteis sem movimento: 2026-10-05, 2026-10-06"))
    c.close()
    itens = get(cli, "/api/v1/rodadas").json()["dados"]["itens"]
    r = next(x for x in itens if x["id"] == rid)
    assert r["conferida"] is False
    assert r["reprovadas"] == [{"conta": "C6 PJ", "tipo": "dias_sem_buraco", "detalhe": "dias úteis sem movimento: 2026-10-05, 2026-10-06"}]


def test_rodada_conferida_nao_tem_reprovadas(cli):
    itens = get(cli, "/api/v1/rodadas").json()["dados"]["itens"]
    assert all(x["reprovadas"] == [] for x in itens if x["conferida"])


def test_lista_de_sugestoes_aceita_regra_sem_categoria_e_aprovar_sem_escolher_da_400(cli, banco):
    from gabi.dinheiro.regras import criar_sugestao
    c = conectar(banco)
    sid = criar_sugestao(c, "regra", None, {"padrao": "BEKAA", "acao": {"categoria_id": None}}, "3 PIX para BEKAA sem categoria; escolha a categoria")
    c.close()
    r = get(cli, "/api/v1/sugestoes")
    assert r.status_code == 200
    item = next(i for i in r.json()["dados"]["itens"] if i["id"] == sid)
    assert item["payload"]["acao"] == {"categoria_id": None} and item["impacto"] is None   # sem categoria, não há o que contar
    assert post(cli, f"/api/v1/sugestoes/{sid}/aprovar", {}).status_code == 400


def test_projecao_do_caixa_formata_valores_e_aponta_o_menor_saldo(cli):
    r = get(cli, "/api/v1/caixa/projecao?dias=6")
    assert r.status_code == 200
    d = r.json()["dados"]
    assert d["saldo_inicial"] == "12345.60" and len(d["dias"]) == 6
    hoje = d["dias"][0]
    assert (hoje["dia"], hoje["saidas"], hoje["saldo"]) == ("2026-10-08", "1300.00", "11045.60")   # IPTU atrasado + condomínio saem hoje
    luz = next(x for x in d["dias"] if x["dia"] == "2026-10-12")
    assert luz["saidas"] == "230.50" and luz["saldo"] == "10815.10"
    assert d["menor_saldo"] == {"dia": "2026-10-12", "saldo": "10815.10"} and "Nibo" in d["aviso"]


def test_projecao_valida_o_horizonte_e_so_o_boss_ve(cli):
    assert get(cli, "/api/v1/caixa/projecao?dias=0").status_code == 400
    assert get(cli, "/api/v1/caixa/projecao?dias=91").status_code == 400
    assert get(cli, "/api/v1/caixa/projecao", h=VIP).status_code == 403


def test_rumo_traz_os_12_meses_e_exige_boss(cli):
    d = get(cli, "/api/v1/rumo?ano=2026").json()["dados"]
    assert d["ano"] == 2026 and len(d["meses"]) == 12 and d["meses"][0]["mes"] == "2026-01"
    assert get(cli, "/api/v1/rumo", VIP).status_code == 403 and get(cli, "/api/v1/rumo?ano=1").status_code == 400
