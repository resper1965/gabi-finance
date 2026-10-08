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
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado, limite_centavos) values ('b1','C6','BANK','C6 PJ','a_decidir',NULL)")
    c.execute("insert into pessoa(id, nome, papel, telefone, dados) values ('lia','Lia','filha','+5511900000003', ?)",
              (json.dumps({"documentos": [{"tipo": "CPF", "numero": "***.***.***-09"}]}),))
    c.execute("insert into empresa(id, nome, cnpj) values ('ness','Ness','12.345.678/0001-90')")
    c.execute("insert into categoria(nome) values ('Mercado')")
    c.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def req(cli, metodo, url, corpo=None, h=BOSS):
    kw = {"headers": {**h, **JSON}}
    if corpo is not None:
        kw["content"] = json.dumps(corpo)
    return cli.request(metodo, url, **kw)


def itens(r):
    return r.json()["dados"]["itens"]


# ---------------- escopo, auditoria ----------------
@pytest.mark.parametrize("tipo", ["empresas", "contas", "pessoas", "compromissos", "categorias"])
def test_so_boss_acessa(cli, tipo):
    assert cli.get(f"/api/v1/cadastros/{tipo}", headers=VIP).status_code == 403 and cli.get(f"/api/v1/cadastros/{tipo}").status_code == 401


def test_tipo_desconhecido_404(cli):
    assert req(cli, "GET", "/api/v1/cadastros/coisas").status_code == 404


def test_toda_mudanca_vira_decisao(cli, banco):
    req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "Bekaa", "cnpj": "11.222.333/0001-81"})
    req(cli, "PATCH", "/api/v1/cadastros/empresas/ness", {"cnpj": "99.999.999/0001-99"})
    req(cli, "DELETE", "/api/v1/cadastros/empresas/ness")
    d = [r["o_que"] for r in conectar(banco).execute("select o_que from decisao where origem='cadastros' order by id")]
    assert len(d) == 3 and "criada" in d[0] and "alterada" in d[1] and "excluída" in d[2]


def test_mudanca_cross_site_recusada(cli):
    r = cli.post("/api/v1/cadastros/empresas", headers={**BOSS, **JSON, "Sec-Fetch-Site": "cross-site"}, content=json.dumps({"nome": "X"}))
    assert r.status_code == 403


# ---------------- empresas / pessoas ----------------
def test_empresa_cria_com_id_a_partir_do_nome_e_evita_colisao(cli):
    a = req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "Bekaa Tecnologia Ltda."})
    b = req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "Bekaa Tecnologia Ltda."})
    assert a.status_code == 201 and a.json()["dados"]["id"] == "bekaa-tecnologia-ltda"
    assert b.status_code == 201 and b.json()["dados"]["id"] == "bekaa-tecnologia-ltda-2"


def test_empresa_com_dados_extras_e_relacao_valida(cli):
    r = req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "Ionic", "dados": {"relacao": "contratante", "dominios": ["ionic.health"]}})
    assert r.status_code == 201 and r.json()["dados"]["dados"]["relacao"] == "contratante"
    assert req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "X", "dados": {"relacao": "inventada"}}).status_code == 400
    assert req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "X", "dados": "texto"}).status_code == 400


def test_nome_obrigatorio_e_campo_desconhecido(cli):
    assert req(cli, "POST", "/api/v1/cadastros/empresas", {}).status_code == 400
    assert req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "  "}).status_code == 400
    assert req(cli, "POST", "/api/v1/cadastros/empresas", {"nome": "X", "coisa": 1}).status_code == 400


def test_get_patch_e_exclusao_logica(cli, banco):
    assert req(cli, "GET", "/api/v1/cadastros/empresas/ness").json()["dados"]["nome"] == "Ness"
    assert req(cli, "PATCH", "/api/v1/cadastros/empresas/ness", {"nome": "Ness Tecnologia"}).json()["dados"]["nome"] == "Ness Tecnologia"
    assert req(cli, "DELETE", "/api/v1/cadastros/empresas/ness").status_code == 200
    assert [i["id"] for i in itens(req(cli, "GET", "/api/v1/cadastros/empresas"))] == []
    assert [i["id"] for i in itens(req(cli, "GET", "/api/v1/cadastros/empresas?incluir_excluidos=true"))] == ["ness"]
    assert conectar(banco).execute("select excluido_em from empresa where id='ness'").fetchone()[0] is not None  # nada é apagado (R10)
    assert req(cli, "GET", "/api/v1/cadastros/empresas/ness").status_code == 404


def test_404_em_id_inexistente(cli):
    for m in ("GET", "PATCH", "DELETE"):
        assert req(cli, m, "/api/v1/cadastros/empresas/nada", {"nome": "x"} if m == "PATCH" else None).status_code == 404


def test_busca_por_nome(cli):
    req(cli, "POST", "/api/v1/cadastros/pessoas", {"nome": "Ana Souza"})
    assert [i["id"] for i in itens(req(cli, "GET", "/api/v1/cadastros/pessoas?busca=ana"))] == ["ana-souza"]


def test_cpf_so_devolve_mascarado_e_audita(cli, banco):
    r = req(cli, "GET", "/api/v1/cadastros/pessoas/lia/cpf")
    assert r.status_code == 200 and r.json()["dados"]["documentos"] == [{"tipo": "CPF", "numero": "***.***.***-09"}]
    d = conectar(banco).execute("select quem, o_que from decisao where origem='cadastros' order by id desc limit 1").fetchone()
    assert d["quem"] == "boss@x.com" and "lia" in d["o_que"] and "documento" in d["o_que"]
    assert req(cli, "GET", "/api/v1/cadastros/pessoas/nada/cpf").status_code == 404


# ---------------- contas (G5: o que entra no caixa único) ----------------
def test_conta_liberar_no_caixa_unico(cli, banco):
    c = conectar(banco)
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,'2026-10-08T14:00:00', 100000)")
    c.close()
    assert req(cli, "GET", "/api/v1/caixa/resumo").json()["dados"]["kpis"]["saldo"] == "0.00"  # a_decidir não conta
    r = req(cli, "PATCH", "/api/v1/cadastros/contas/1", {"estado": "sim", "apelido": "C6 PJ (caixa)"})
    assert r.status_code == 200 and r.json()["dados"]["estado"] == "sim"
    assert req(cli, "GET", "/api/v1/caixa/resumo").json()["dados"]["kpis"]["saldo"] == "1000.00"


def test_conta_estado_invalido_400(cli):
    assert req(cli, "PATCH", "/api/v1/cadastros/contas/1", {"estado": "talvez"}).status_code == 400


def test_conta_da_fonte_nao_muda_instituicao_nem_tipo(cli):
    assert req(cli, "PATCH", "/api/v1/cadastros/contas/1", {"instituicao": "Outro"}).status_code == 400
    assert req(cli, "PATCH", "/api/v1/cadastros/contas/1", {"tipo": "CREDIT"}).status_code == 400


def test_conta_manual_pode_ser_criada(cli):
    r = req(cli, "POST", "/api/v1/cadastros/contas", {"apelido": "Dinheiro vivo", "instituicao": "Carteira", "tipo": "BANK"})
    assert r.status_code == 201 and r.json()["dados"]["externo_id"].startswith("manual-") and r.json()["dados"]["estado"] == "a_decidir"
    assert req(cli, "POST", "/api/v1/cadastros/contas", {"apelido": "X", "tipo": "OUTRO"}).status_code == 400


# ---------------- categorias e equivalências ----------------
def test_categoria_nome_unico_e_hierarquia(cli):
    r = req(cli, "POST", "/api/v1/cadastros/categorias", {"nome": "Supermercado", "pai_id": 1})
    assert r.status_code == 201 and r.json()["dados"]["pai_id"] == 1
    assert req(cli, "POST", "/api/v1/cadastros/categorias", {"nome": "Mercado"}).status_code == 409
    assert req(cli, "POST", "/api/v1/cadastros/categorias", {"nome": "Órfã", "pai_id": 999}).status_code == 400


def test_equivalencia_de_categorias(cli):
    assert itens(req(cli, "GET", "/api/v1/cadastros/categorias/equivalencias")) == []
    assert req(cli, "PUT", "/api/v1/cadastros/categorias/equivalencias", {"origem_pluggy": "Groceries", "categoria_id": 1}).status_code == 200
    assert req(cli, "PUT", "/api/v1/cadastros/categorias/equivalencias", {"origem_pluggy": "Groceries", "categoria_id": 1}).status_code == 200  # idempotente
    assert itens(req(cli, "GET", "/api/v1/cadastros/categorias/equivalencias")) == [{"origem_pluggy": "Groceries", "categoria_id": 1}]
    assert req(cli, "PUT", "/api/v1/cadastros/categorias/equivalencias", {"origem_pluggy": "X", "categoria_id": 999}).status_code == 400
    assert req(cli, "DELETE", "/api/v1/cadastros/categorias/equivalencias/Groceries").status_code == 200
    assert itens(req(cli, "GET", "/api/v1/cadastros/categorias/equivalencias")) == []


def test_equivalencia_aplicada_pela_classificacao(cli, banco):
    from gabi.dinheiro.classificar import classificar
    req(cli, "PUT", "/api/v1/cadastros/categorias/equivalencias", {"origem_pluggy": "Groceries", "categoria_id": 1})
    c = conectar(banco)
    c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_banco) values (1,'x','2026-10-08',-100,'LOJA','Groceries')")
    classificar(c, 1)
    assert c.execute("select categoria_id, categoria_origem from lancamento").fetchone()[:] == (1, "banco")


# ---------------- compromissos (substituem a planilha) ----------------
NOVO = {"nome": "Aluguel", "extrato": "IMOBILIARIA SUL", "vencimento": "dia:5", "valor_tipo": "fixo", "valor_padrao": "2.000,00", "forma": "pix", "apelidos": ["IMOB SUL"]}


def test_compromisso_cria_valida_e_gera_o_mes(cli, banco):
    r = req(cli, "POST", "/api/v1/cadastros/compromissos", NOVO)
    assert r.status_code == 201
    d = r.json()["dados"]
    assert d["id"] == "aluguel" and d["valor_padrao"] == "2000.00" and d["apelidos"] == ["IMOB SUL"] and d["ativo"] is True
    comp = [x["id"] for x in conectar(banco).execute("select id from compromisso order by id")]
    assert "aluguel:2026-10" in comp and "aluguel:2026-11" in comp  # recalculou na hora


@pytest.mark.parametrize("ruim", [{"vencimento": "45"}, {"forma": "cheque"}, {"valor_tipo": "estranho"}, {"valor_padrao": "abc"}, {"extrato": ""}, {"ajuste_dia_util": "pula"},
                                  {"valido_de": "2026-12", "valido_ate": "2026-01"}])
def test_compromisso_invalido_400_e_nada_grava(cli, banco, ruim):
    assert req(cli, "POST", "/api/v1/cadastros/compromissos", {**NOVO, **ruim}).status_code == 400
    assert conectar(banco).execute("select count(*) from compromisso_linha").fetchone()[0] == 0


def test_compromisso_id_duplicado_409(cli):
    req(cli, "POST", "/api/v1/cadastros/compromissos", NOVO)
    assert req(cli, "POST", "/api/v1/cadastros/compromissos", {**NOVO, "id": "aluguel"}).status_code == 409


def test_compromisso_patch_muda_e_recalcula(cli, banco):
    req(cli, "POST", "/api/v1/cadastros/compromissos", NOVO)
    r = req(cli, "PATCH", "/api/v1/cadastros/compromissos/aluguel", {"valor_padrao": "2500"})
    assert r.status_code == 200 and r.json()["dados"]["valor_padrao"] == "2500.00"
    assert conectar(banco).execute("select valor_centavos from compromisso where id='aluguel:2026-11'").fetchone()[0] == 250000


def test_compromisso_patch_que_invalida_a_linha_400_e_mantem_a_antiga(cli):
    req(cli, "POST", "/api/v1/cadastros/compromissos", NOVO)
    assert req(cli, "PATCH", "/api/v1/cadastros/compromissos/aluguel", {"vencimento": "99"}).status_code == 400
    assert req(cli, "GET", "/api/v1/cadastros/compromissos/aluguel").json()["dados"]["vencimento"] == "dia:5"


def test_compromisso_desativar_e_excluir_somem_da_agenda(cli, banco):
    req(cli, "POST", "/api/v1/cadastros/compromissos", NOVO)
    req(cli, "PATCH", "/api/v1/cadastros/compromissos/aluguel", {"ativo": False})
    from gabi.dinheiro.repositorio import ler_leitura
    assert [l["id"] for l in ler_leitura(conectar(banco))["linhas"]] == []
    req(cli, "PATCH", "/api/v1/cadastros/compromissos/aluguel", {"ativo": True})
    assert req(cli, "DELETE", "/api/v1/cadastros/compromissos/aluguel").status_code == 200
    assert [l["id"] for l in ler_leitura(conectar(banco))["linhas"]] == []
    assert conectar(banco).execute("select count(*) from compromisso_linha").fetchone()[0] == 1  # exclusão lógica


def test_categoria_nao_pode_ser_pai_de_si_mesma(cli):
    assert req(cli, "PATCH", "/api/v1/cadastros/categorias/1", {"pai_id": 1}).status_code == 400
    assert req(cli, "GET", "/api/v1/cadastros/categorias/1").json()["dados"]["pai_id"] is None


def test_serie_de_compromisso_com_validades_sobrepostas_e_recusada(cli):
    base = {**NOVO, "id": "aluguel", "valido_de": "2026-01", "valido_ate": "2026-12"}
    assert req(cli, "POST", "/api/v1/cadastros/compromissos", base).status_code == 201
    # reajuste "a partir de novembro" na mesma série, mas sem fechar a validade da linha antiga: sobrepõe
    r = req(cli, "POST", "/api/v1/cadastros/compromissos", {**NOVO, "id": "aluguel-202611", "valido_de": "2026-11", "valor_padrao": "2200"})
    assert r.status_code == 400 and "sobrep" in r.json()["mensagem"]
    # fechando a antiga em outubro, a nova passa
    assert req(cli, "PATCH", "/api/v1/cadastros/compromissos/aluguel", {"valido_ate": "2026-10"}).status_code == 200
    assert req(cli, "POST", "/api/v1/cadastros/compromissos", {**NOVO, "id": "aluguel-202611", "valido_de": "2026-11", "valor_padrao": "2200"}).status_code == 201
