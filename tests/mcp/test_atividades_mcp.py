"""Atividades pelo MCP (ADR-033): as 5 ferramentas só chamam `gabi.atividades`, gravam `decisao` origem hermes e devolvem `desfazer`.
Consome: gabi.mcp.ferramentas_atividades, fixtures de tests/mcp/test_servidor.py (AGORA = 08/10/2026 15:00 BRT)."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, rpc  # noqa: F401  (fixtures e helpers)

NOMES = ("atividade_criar", "atividade_listar", "atividade_concluir", "atividade_adiar", "atividade_cancelar")


@pytest.fixture
def cli_tok(banco):
    c = conectar(banco)
    tok = {"atv": emitir(c, "hermes", ["atividades"]), "fin": emitir(c, "so-fin", ["fin"])}
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        yield cli, tok


def _decisoes(banco):
    c = conectar(banco)
    try:
        return [tuple(r) for r in c.execute("select quem, origem from decisao where o_que like 'atividade%' order by id")]
    finally:
        c.close()


def _c(cli, tok, ferramenta, **args):
    r = rpc(cli, tok["atv"], "tools/call", {"name": ferramenta, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    corpo = json.loads(res["content"][0]["text"]) if res.get("content") else res
    return corpo if "erro" in corpo else corpo["dados"]  # sucesso vem no envelope {"dados": ..., "dados_ate": ...}


def test_sem_escopo_atividades_recusa(cli_tok):
    cli, tok = cli_tok
    args = {"atividade_criar": {"texto": "x"}, "atividade_listar": {}, "atividade_concluir": {"atividade": "x"}, "atividade_adiar": {"atividade": "x", "vence": "2026-11-01"},
            "atividade_cancelar": {"atividade": "x"}}
    for ferramenta, a in args.items():
        r = rpc(cli, tok["fin"], "tools/call", {"name": ferramenta, "arguments": a})
        res = r.json()["result"]
        corpo = json.loads(res["content"][0]["text"]) if res.get("content") else res
        assert corpo.get("erro") == "sem_escopo", ferramenta


def test_criar_lista_adiar_concluir_e_cancelar(banco, cli_tok):
    cli, tok = cli_tok
    a = _c(cli, tok, "atividade_criar", texto="ligar pro contador", vence="2026-10-10T10:00")
    assert a["status"] == "aberta" and a["vence_em"] == "2026-10-10T10:00" and a["desfazer"] == f"atividade_cancelar({a['id']})"
    assert [i["id"] for i in _c(cli, tok, "atividade_listar")["itens"]] == [a["id"]]
    assert _c(cli, tok, "atividade_adiar", atividade="contador", vence="2026-10-12")["vence_em"] == "2026-10-12"
    assert _c(cli, tok, "atividade_concluir", atividade=str(a["id"]))["status"] == "feita"
    b = _c(cli, tok, "atividade_criar", texto="pagar a luz")
    assert _c(cli, tok, "atividade_cancelar", atividade="luz")["status"] == "cancelada" and b["status"] == "aberta"
    assert _decisoes(banco) == [("hermes", "hermes")] * 5


def test_criar_repetido_devolve_a_existente(banco, cli_tok):
    cli, tok = cli_tok
    a = _c(cli, tok, "atividade_criar", texto="ligar pro contador", vence="2026-10-10")
    b = _c(cli, tok, "atividade_criar", texto="Ligar pro contador", vence="2026-10-10")
    assert b["id"] == a["id"] and b["ja_existia"] is True and len(_decisoes(banco)) == 1


def test_resolucao_por_trecho_ambiguo_e_inexistente(cli_tok):
    cli, tok = cli_tok
    _c(cli, tok, "atividade_criar", texto="ligar pro contador"); _c(cli, tok, "atividade_criar", texto="ligar pro dentista")
    r = _c(cli, tok, "atividade_concluir", atividade="ligar")
    assert r["erro"] == "ambiguo" and "contador" in r["mensagem"] and "dentista" in r["mensagem"]
    assert _c(cli, tok, "atividade_concluir", atividade="academia")["erro"] == "nao_encontrado"
    assert _c(cli, tok, "atividade_concluir", atividade="999")["erro"] == "nao_encontrado"


def test_data_passada_e_erro_legivel_e_nao_grava(banco, cli_tok):
    cli, tok = cli_tok
    r = _c(cli, tok, "atividade_criar", texto="ligar", vence="2026-10-01")
    assert r["erro"] == "requisicao_invalida" and "passou" in r["mensagem"] and _decisoes(banco) == []
    assert _c(cli, tok, "atividade_criar", texto="   ")["erro"] == "requisicao_invalida"
    assert _c(cli, tok, "atividade_listar", status="outra")["erro"] == "requisicao_invalida"


def test_desfazer_do_adiar_com_vencimento_antigo_ja_passado_nao_promete_o_impossivel(banco, cli_tok):
    cli, tok = cli_tok
    c = conectar(banco)
    c.execute("insert into atividade(texto, vence_em, tem_hora, origem, criada_em) values ('ligar pro contador','2026-10-07T13:00:00+00:00',1,'hermes','x')")
    c.close()
    r = _c(cli, tok, "atividade_adiar", atividade="contador", vence="2026-10-12")
    assert "já passou" in r["desfazer"] and "atividade_adiar" in r["desfazer"] and '"2026-10-07T10:00")' not in r["desfazer"]
