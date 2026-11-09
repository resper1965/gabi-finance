"""Assistente proativo pelo MCP (ADR-037): 4 ferramentas só de leitura, cada uma com o escopo certo; `promessas_candidatas` lê o que o Ricardo enviou pela ponte.
Consome: gabi.mcp.ferramentas_assistente, fixtures de tests/mcp/test_servidor.py (AGORA = 08/10/2026 15:00 BRT)."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.mcp import ferramentas_assistente as fa
from gabi.mcp.ferramentas_prop import ErroFerramenta
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, rpc  # noqa: F401  (fixtures e helpers)


class Ponte:
    def __init__(self, msgs=None, erro=False):
        self.msgs, self.erro, self.chamadas = msgs or [], erro, []

    def enviados_textos(self, conta, dias, limite):
        self.chamadas.append((conta, dias, limite))
        if self.erro:
            raise ErroGoogleOAuth("messages.get -> 500 SEGREDO")
        return self.msgs


def _fontes(con, *contas):
    for i, (conta, prov, estado) in enumerate(contas, 1):
        con.execute("insert into email_fonte(id, conta, provedor, estado) values (?,?,?,?)", (i, conta, prov, estado))


MSG = {"externo_id": "a1", "quando": "2026-10-07T10:00:00+00:00", "para": ["ana@x.com"], "assunto": "Proposta", "trecho": "Te mando até sexta."}


def test_promessas_le_so_contas_ligadas_e_junta_ordenado(banco):
    con = conectar(banco)
    _fontes(con, ("a@gmail.com", "google", "sim"), ("r@ness.com.br", "graph", "sim"), ("off@gmail.com", "google", "nao"))
    g, n = Ponte([MSG]), Ponte([{**MSG, "assunto": "Mais novo", "quando": "2026-10-08T10:00:00+00:00"}])
    r = fa.promessas_candidatas(con, {"google": g, "graph": n}, 7)
    assert [i["assunto"] for i in r["itens"]] == ["Mais novo", "Proposta"] and r["itens"][0]["conta"] == "r@ness.com.br"
    assert r["contas_lidas"] == ["a@gmail.com", "r@ness.com.br"] and r["contas_com_falha"] == []
    assert g.chamadas == [("a@gmail.com", 7, 30)] and "terceiros" in r["aviso"]
    assert "atividade_criar" in r["como_usar"] and "externo_id" not in r["itens"][0]  # id interno não sai


def test_promessas_uma_conta_cai_a_outra_responde_todas_caem_e_erro(banco):
    con = conectar(banco)
    _fontes(con, ("a@gmail.com", "google", "sim"), ("r@ness.com.br", "graph", "sim"))
    r = fa.promessas_candidatas(con, {"google": Ponte(erro=True), "graph": Ponte([MSG])}, 7)
    assert r["contas_com_falha"] == ["a@gmail.com"] and len(r["itens"]) == 1
    with pytest.raises(ErroFerramenta) as e:
        fa.promessas_candidatas(con, {"google": Ponte(erro=True), "graph": Ponte(erro=True)}, 7)
    assert e.value.codigo == "fonte_indisponivel" and "SEGREDO" not in str(e.value)


def test_promessas_sem_conta_ligada_devolve_vazio_e_dias_invalidos(banco):
    con = conectar(banco)
    assert fa.promessas_candidatas(con, {}, 7)["itens"] == []
    for dias in (0, 15, True, "7"):
        with pytest.raises(ValueError):
            fa.promessas_candidatas(con, {}, dias)


@pytest.fixture
def cli_tok(banco):
    c = conectar(banco)
    tok = {"trab": emitir(c, "hermes", ["trabalho", "fin"]), "so_fin": emitir(c, "so-fin", ["fin"]), "so_trab": emitir(c, "so-trab", ["trabalho"])}
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        yield cli, tok


def _chamar(cli, token, ferramenta, **args):
    r = rpc(cli, token, "tools/call", {"name": ferramenta, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return json.loads(res["content"][0]["text"]) if res.get("content") else res


def test_pelo_mcp_cada_ferramenta_com_seu_escopo(cli_tok):
    cli, tok = cli_tok
    f = _chamar(cli, tok["trab"], "olhar_a_frente")
    assert f["dados"]["ha_alerta"] in (True, False) and "caixa" in f["dados"]
    assert "atividades" in _chamar(cli, tok["trab"], "revisao_semana")["dados"]
    assert _chamar(cli, tok["trab"], "preparar_reuniao")["dados"]["evento"] is None
    # sem escopo: olhar_a_frente pede `fin`; as outras pedem `trabalho`
    assert _chamar(cli, tok["so_trab"], "olhar_a_frente")["erro"] == "sem_escopo"
    assert _chamar(cli, tok["so_fin"], "revisao_semana")["erro"] == "sem_escopo"
    assert _chamar(cli, tok["so_fin"], "promessas_candidatas")["erro"] == "sem_escopo"
