"""Projetos pelo MCP (ADR-034): as 10 ferramentas `projeto_*`/`anexo_recentes` só chamam `gabi.projetos`, gravam `decisao` origem hermes e exigem o escopo `projetos`.
Consome: gabi.mcp.ferramentas_projetos, fixtures de tests/mcp/test_servidor.py (AGORA = 08/10/2026 15:00 BRT)."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, rpc  # noqa: F401  (fixtures e helpers)

NOMES = ("projeto_criar", "projeto_ligar", "projeto_listar", "projeto_ver", "projeto_atualizar", "projeto_pessoa", "projeto_gasto", "projeto_fato", "projeto_fatos", "anexo_recentes", "projeto_anexar")


@pytest.fixture
def cli_tok(banco):
    c = conectar(banco)
    tok = {"pj": emitir(c, "hermes", ["projetos", "atividades"]), "fin": emitir(c, "so-fin", ["fin"])}
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        yield cli, tok


def _decisoes(banco):
    c = conectar(banco)
    try:
        return [tuple(r) for r in c.execute("select quem, origem from decisao where o_que like 'projeto%' or o_que like 'atividade%' order by id")]
    finally:
        c.close()


def _c(cli, tok, ferramenta, **args):
    r = rpc(cli, tok["pj"], "tools/call", {"name": ferramenta, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    corpo = json.loads(res["content"][0]["text"]) if res.get("content") else res
    return corpo if "erro" in corpo else corpo["dados"]


def test_sem_escopo_projetos_recusa_as_onze(cli_tok):
    cli, tok = cli_tok
    args = {"projeto_criar": {"nome": "x"}, "projeto_ligar": {"linear_id": "L", "linear_url": "https://x", "nome": "x"}, "projeto_listar": {}, "projeto_ver": {"projeto": "x"}, "projeto_atualizar": {"projeto": "x"}, "projeto_pessoa": {"projeto": "x", "nome": "y"},
            "projeto_gasto": {"projeto": "x", "valor": "1,00"}, "projeto_fato": {"projeto": "x", "texto": "y"}, "projeto_fatos": {"projeto": "x"}, "anexo_recentes": {}, "projeto_anexar": {"projeto": "x", "anexo_id": 1}}
    assert set(args) == set(NOMES)
    for ferramenta, a in args.items():
        res = rpc(cli, tok["fin"], "tools/call", {"name": ferramenta, "arguments": a}).json()["result"]
        corpo = json.loads(res["content"][0]["text"]) if res.get("content") else res
        assert corpo.get("erro") == "sem_escopo", ferramenta


def test_fluxo_completo(banco, cli_tok):
    cli, tok = cli_tok
    p = _c(cli, tok, "projeto_criar", nome="Carro na oficina", objetivo="trocar o motor", prazo="2026-11-20", orcamento="5000,00",
           atividades=[{"texto": "pedir orçamento", "vence": "2026-10-10"}, {"texto": "aprovar o serviço", "depois_de": 1}, {"texto": "buscar o carro", "marco": True}])
    assert p["nome"] == "Carro na oficina" and p["orcamento"] == "5000.00" and p["progresso"] == {"feitas": 0, "total": 3} and [a["texto"] for a in p["bloqueadas"]] == ["aprovar o serviço"]
    assert "projeto_atualizar" in p["desfazer"]
    assert [i["id"] for i in _c(cli, tok, "projeto_listar")["itens"]] == [p["id"]]
    assert _c(cli, tok, "projeto_pessoa", projeto="carro", nome="Seu Jorge", papel="mecânico", contato="11 99999-0000")["papel"] == "mecânico"
    g = _c(cli, tok, "projeto_gasto", projeto="oficina", valor="1200,50", descricao="peça")
    assert g["valor"] == "1200.50"
    f = _c(cli, tok, "projeto_fato", projeto=str(p["id"]), texto="O mecânico disse que o prazo é dia 20", pessoa="Seu Jorge")
    assert f["data"] == "2026-10-08" and f["origem"] == "hermes"
    assert [x["texto"] for x in _c(cli, tok, "projeto_fatos", projeto="carro", texto="PRAZO")["itens"]] == [f["texto"]]
    ver = _c(cli, tok, "projeto_ver", projeto="carro")
    assert ver["gasto"] == "1200.50" and ver["saldo"] == "3799.50" and ver["fatos_recentes"][0]["id"] == f["id"] and [x["nome"] for x in ver["pessoas"]] == ["Seu Jorge"]
    c = conectar(banco)
    a = c.execute("insert into anexo(tipo, arquivo, sha256, transcricao, recebido_em) values ('audio','aa/a.ogg','a','oi, o carro fica pronto',?)", (AGORA.isoformat(),)).lastrowid
    c.close()
    assert [x["transcricao"] for x in _c(cli, tok, "anexo_recentes")["itens"]] == ["oi, o carro fica pronto"]
    assert _c(cli, tok, "projeto_anexar", projeto="carro", anexo_id=a)["projeto_id"] == p["id"]
    assert _c(cli, tok, "anexo_recentes")["itens"] == []
    assert _c(cli, tok, "projeto_anexar", projeto="carro", paperless_id=77)["tipo"] == "documento"
    assert _c(cli, tok, "projeto_ver", projeto="carro")["anexos"] == 2
    r = _c(cli, tok, "projeto_atualizar", projeto="carro", status="concluido")
    assert r["status"] == "concluido" and "não reabre" in r["desfazer"]
    assert set(_decisoes(banco)) == {("hermes", "hermes")}


def test_ambiguo_e_inexistente(cli_tok):
    cli, tok = cli_tok
    _c(cli, tok, "projeto_criar", nome="Carro do Ricardo")
    _c(cli, tok, "projeto_criar", nome="Carro da Louise")
    r = _c(cli, tok, "projeto_ver", projeto="carro")
    assert r["erro"] == "ambiguo" and "Ricardo" in r["mensagem"] and "Louise" in r["mensagem"]
    assert _c(cli, tok, "projeto_ver", projeto="barco")["erro"] == "nao_encontrado"
    assert _c(cli, tok, "projeto_ver", projeto="999")["erro"] == "nao_encontrado"


def test_erros_legiveis_e_nao_gravam(banco, cli_tok):
    cli, tok = cli_tok
    assert _c(cli, tok, "projeto_criar", nome="  ")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_criar", nome="X", atividades=[{"texto": "a", "depois_de": 2}])["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_criar", nome="X", orcamento="abc")["erro"] == "valor_invalido"
    assert _decisoes(banco) == []
    p = _c(cli, tok, "projeto_criar", nome="Obra")
    assert _c(cli, tok, "projeto_gasto", projeto="obra", valor="1.500")["erro"] == "valor_invalido"
    assert _c(cli, tok, "projeto_gasto", projeto="obra")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_fato", projeto="obra", texto="")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_anexar", projeto="obra")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_listar", status="lixo")["erro"] == "requisicao_invalida"
    _c(cli, tok, "projeto_atualizar", projeto=str(p["id"]), status="cancelado")
    r = _c(cli, tok, "projeto_atualizar", projeto=str(p["id"]), status="ativo")
    assert r["erro"] == "requisicao_invalida" and "reabre" in r["mensagem"]


def test_atividade_do_hermes_nao_oferece_projeto_depois_de_nem_marco(cli_tok):
    cli, tok = cli_tok  # ADR-038: o esquema que o Hermes vê não tem os parâmetros (o servidor ignora argumento extra, por isso a garantia é o esquema)
    ferramentas = {t["name"]: t for t in rpc(cli, tok["pj"], "tools/list", {}).json()["result"]["tools"]}
    assert set(ferramentas["atividade_criar"]["inputSchema"]["properties"]) == {"texto", "vence"}
    assert set(ferramentas["atividade_listar"]["inputSchema"]["properties"]) == {"status"}


def test_projeto_ligar_cria_e_e_idempotente(cli_tok, banco):
    cli, tok = cli_tok
    a = _c(cli, tok, "projeto_ligar", linear_id="LIN-1", linear_url="https://linear.app/r/project/fazenda", nome="Vender a fazenda")
    b = _c(cli, tok, "projeto_ligar", linear_id="LIN-1", linear_url="https://linear.app/r/project/fazenda", nome="Vender a fazenda")
    assert a["id"] == b["id"] and a["linear_url"] == "https://linear.app/r/project/fazenda"
    assert _c(cli, tok, "projeto_ver", projeto="fazenda")["linear_url"] == a["linear_url"]
    assert _c(cli, tok, "projeto_listar")["itens"][0]["linear_url"] == a["linear_url"]
    assert ("hermes", "hermes") in _decisoes(banco)


def test_projeto_ligar_liga_existente_por_nome(cli_tok):
    cli, tok = cli_tok
    p = _c(cli, tok, "projeto_criar", nome="Reforma da casa")
    r = _c(cli, tok, "projeto_ligar", projeto="reforma", linear_id="LIN-2", linear_url="https://linear.app/r/project/reforma")
    assert r["id"] == p["id"] and r["linear_id"] == "LIN-2"


def test_projeto_ligar_erros(cli_tok):
    cli, tok = cli_tok
    assert _c(cli, tok, "projeto_ligar", linear_id="", linear_url="https://x", nome="a")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_ligar", linear_id="L", linear_url="http://x", nome="a")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "projeto_ligar", projeto="nada", linear_id="L", linear_url="https://x")["erro"] == "nao_encontrado"
    _c(cli, tok, "projeto_criar", nome="Carro azul")
    _c(cli, tok, "projeto_criar", nome="Carro verde")
    assert _c(cli, tok, "projeto_ligar", projeto="carro", linear_id="L", linear_url="https://x")["erro"] == "ambiguo"
