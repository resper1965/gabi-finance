"""Despesas pelo MCP (ADR-032): as 6 ferramentas só chamam `dinheiro.despesas`, gravam `decisao` origem hermes e devolvem `desfazer`.
Consome: gabi.mcp.ferramentas_despesas, fixtures de tests/mcp/test_servidor.py (AGORA = 08/10/2026)."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, rpc  # noqa: F401  (fixtures e helpers)


@pytest.fixture
def cli_tok(banco):
    c = conectar(banco)
    tok = {"fin": emitir(c, "hermes", ["fin"]), "sem_fin": emitir(c, "so-propostas", ["propostas"])}
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        yield cli, tok


def _decisoes(banco):
    c = conectar(banco)
    try:
        return [tuple(r) for r in c.execute("select quem, origem, o_que from decisao order by id")]
    finally:
        c.close()


def chamar(cli, token, ferramenta, **args):
    """Como o `chamar` de test_servidor, mas aceita o argumento `nome` (o de despesa_criar)."""
    r = rpc(cli, token, "tools/call", {"name": ferramenta, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return json.loads(res["content"][0]["text"]) if res.get("content") else res


def _c(cli, tok, ferramenta, **args):
    return chamar(cli, tok["fin"], ferramenta, **args)


def test_criar_fixa_com_valor_ditado_grava_e_audita(banco, cli_tok):
    cli, tok = cli_tok
    d = _c(cli, tok, "despesa_criar", nome="Sabrina", valor="1500,00", dia=10, forma="pix")["dados"]
    assert d["id"] == "sabrina" and d["valor"] == "1500.00" and d["vencimento"] == "dia:10" and d["tipo"] == "fixa" and d["forma"] == "pix"
    assert d["proximo_vencimento"] >= "2026-10-10"
    assert 'despesa_excluir("sabrina")' in d["desfazer"]
    assert _decisoes(banco) == [("hermes", "hermes", "despesa sabrina criada (fixa)")]


def test_criar_avulsa_por_data(banco, cli_tok):
    cli, tok = cli_tok
    d = _c(cli, tok, "despesa_criar", nome="Dentista", valor="R$ 450,00", data="2026-11-20")["dados"]
    assert d["tipo"] == "avulsa" and d["valido_de"] == d["valido_ate"] == "2026-11" and d["vencimento"] == "dia:20" and d["valor"] == "450.00"


@pytest.mark.parametrize("args, erro", [
    ({"nome": "X", "valor": "1.500", "dia": 5}, "valor_invalido"),
    ({"nome": "X", "valor": "1,500", "dia": 5}, "valor_invalido"),
    ({"nome": "X", "valor": "-10,00", "dia": 5}, "valor_invalido"),
    ({"nome": "X", "valor": "10,00"}, "requisicao_invalida"),
    ({"nome": "X", "valor": "10,00", "dia": 32}, "requisicao_invalida"),
    ({"nome": "X", "valor": "10,00", "dia": 5, "data": "2026-11-20"}, "requisicao_invalida"),
    ({"nome": "X", "valor": "10,00", "dia": 5, "forma": "cheque"}, "requisicao_invalida"),
])
def test_criar_recusa_e_nao_grava(banco, cli_tok, args, erro):
    cli, tok = cli_tok
    assert _c(cli, tok, "despesa_criar", **args)["erro"] == erro
    assert _decisoes(banco) == []


def test_listar_por_texto_e_situacao(banco, cli_tok):
    cli, tok = cli_tok
    c = conectar(banco)  # despesa antiga (sem valido_de), como as da planilha
    c.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_padrao_centavos) values ('luz','Luz','LUZ','dia:12',23050)")
    c.close()
    _c(cli, tok, "despesa_criar", nome="Escola Bia", valor="3000,00", dia=6)
    nomes = [i["nome"] for i in _c(cli, tok, "despesas_listar")["dados"]["itens"]]
    assert nomes == ["Luz", "Escola Bia"]
    assert [i["id"] for i in _c(cli, tok, "despesas_listar", texto="escola")["dados"]["itens"]] == ["escola-bia"]
    _c(cli, tok, "despesa_encerrar", despesa="luz", ultimo_mes="2026-09")
    assert [i["id"] for i in _c(cli, tok, "despesas_listar", situacao="encerrada")["dados"]["itens"]] == ["luz"]
    assert len(_c(cli, tok, "despesas_listar", situacao="todas")["dados"]["itens"]) == 2
    vazio = _c(cli, tok, "despesas_listar", texto="nada disso")["dados"]
    assert vazio["itens"] == [] and vazio["vazio"] is True
    assert _c(cli, tok, "despesas_listar", situacao="outra")["erro"] == "requisicao_invalida"


def test_nome_ambiguo_exato_e_nao_encontrado(cli_tok):
    cli, tok = cli_tok
    for n in ("Escola Bia", "Escola Clara", "Luz", "Luz Casa Praia"):
        _c(cli, tok, "despesa_criar", nome=n, valor="10,00", dia=20)
    r = _c(cli, tok, "despesa_encerrar", despesa="escola")
    assert r["erro"] == "ambiguo" and "escola-bia" in r["mensagem"] and "escola-clara" in r["mensagem"]
    assert _c(cli, tok, "despesa_mudar", despesa="luz", valor="20,00")["dados"]["id"] == "luz"  # nome exato vence o prefixo
    assert _c(cli, tok, "despesa_mudar", despesa="praia", valor="20,00")["dados"]["id"] == "luz-casa-praia"  # trecho
    assert _c(cli, tok, "despesa_mudar", despesa="escola-clara", valor="20,00")["dados"]["id"] == "escola-clara"  # id exato
    assert _c(cli, tok, "despesa_mudar", despesa="Escola B", valor="20,00")["dados"]["id"] == "escola-bia"  # prefixo
    assert _c(cli, tok, "despesa_excluir", despesa="aluguel")["erro"] == "nao_encontrado"


def test_mudar_a_partir_cria_versao_e_desfazer(banco, cli_tok):
    cli, tok = cli_tok
    _c(cli, tok, "despesa_criar", nome="Escola", valor="3000,00", dia=6)
    d = _c(cli, tok, "despesa_mudar", despesa="Escola", valor="3300,00", a_partir="2026-12")["dados"]
    assert d["a_partir"] == "2026-12" and d["nova_versao"] is True and d["valor"] == "3300.00"
    assert 'valor="3000,00"' in d["desfazer"] and 'a_partir="2026-12"' in d["desfazer"]
    assert _decisoes(banco)[-1][:2] == ("hermes", "hermes") and "mudada a partir de 2026-12" in _decisoes(banco)[-1][2]
    assert _c(cli, tok, "despesa_mudar", despesa="escola")["erro"] == "requisicao_invalida"  # nada para mudar
    assert _c(cli, tok, "despesa_mudar", despesa="escola", valor="1.500")["erro"] == "valor_invalido"
    d = _c(cli, tok, "despesa_mudar", despesa="escola", dia=9)["dados"]  # outubro em diante: edita a versão de outubro; a de dezembro fica com o dia dela
    assert [v["vencimento"] for v in d["versoes"]] == ["dia:9", "dia:6"] and d["desfazer"] == 'despesa_mudar("escola", dia=6, a_partir="2026-10") ou Cadastros › Despesas'



def test_mes_valor_dispensar_e_desfazer(banco, cli_tok):
    cli, tok = cli_tok
    _c(cli, tok, "despesa_criar", nome="Sabrina", valor="1500,00", dia=20)
    d = _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-10", valor="500,00")["dados"]
    assert d["mes"] == "2026-10" and 'valor="1500,00"' in d["desfazer"]
    c = conectar(banco)
    assert c.execute("select valor_centavos from compromisso where id='sabrina:2026-10'").fetchone()[0] == 50000
    c.close()
    d = _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-11", dispensar=True)["dados"]
    assert d["dispensado"] is True and 'despesa_mes("sabrina", "2026-11")' in d["desfazer"]
    c = conectar(banco)
    assert c.execute("select 1 from compromisso where id='sabrina:2026-11'").fetchone() is None
    c.close()
    assert _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-11", dispensar=True, valor="1,00")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-11")["dados"]["dispensado"] is False  # desfaz a dispensa
    c = conectar(banco)
    assert c.execute("select 1 from compromisso where id='sabrina:2026-11'").fetchone() is not None
    c.close()
    assert _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-11")["erro"] == "nao_encontrado"  # não estava dispensada
    assert {o for q, og, o in _decisoes(banco) if og == "hermes"} >= {"despesa sabrina dispensada em 2026-11", "despesa sabrina volta em 2026-11 (dispensa desfeita)"}


def test_encerrar_e_excluir(banco, cli_tok):
    cli, tok = cli_tok
    _c(cli, tok, "despesa_criar", nome="Sabrina", valor="1500,00", dia=20)
    _c(cli, tok, "despesa_criar", nome="Errada", valor="1,00", dia=20)
    d = _c(cli, tok, "despesa_encerrar", despesa="sabrina")["dados"]
    assert d["ultimo_mes"] == "2026-09" and "despesa_criar" in d["desfazer"]
    c = conectar(banco)
    assert c.execute("select count(*) from compromisso where linha_id='sabrina'").fetchone()[0] == 0
    c.close()
    d = _c(cli, tok, "despesa_excluir", despesa="Errada")["dados"]
    assert d["excluida"] is True and d["encerrada"] is False and "despesa_criar" in d["desfazer"]
    assert [o for _, og, o in _decisoes(banco) if og == "hermes"][-2:] == ["despesa sabrina encerrada; último mês 2026-09", "despesa errada excluída"]


def test_sem_escopo_fin_recusa(banco, cli_tok):
    cli, tok = cli_tok
    for ferramenta, args in (("despesas_listar", {}), ("despesa_criar", {"nome": "X", "valor": "1,00", "dia": 1})):
        assert chamar(cli, tok["sem_fin"], ferramenta, **args)["erro"] == "sem_escopo"
    assert _decisoes(banco) == []


def test_mes_passado_recusado(banco, cli_tok):
    cli, tok = cli_tok  # AGORA = 08/10/2026
    _c(cli, tok, "despesa_criar", nome="Sabrina", valor="1500,00", dia=20)
    r = _c(cli, tok, "despesa_mes", despesa="sabrina", mes="2026-09", dispensar=True)
    assert r["erro"] == "requisicao_invalida" and "já passou" in r["mensagem"]
