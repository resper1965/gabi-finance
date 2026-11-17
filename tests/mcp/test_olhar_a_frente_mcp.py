"""`olhar_a_frente` pelo MCP (ADR-037): escopo `fin`, só leitura, só caixa e a receber atrasado.
Veio da parte financeira de tests/mcp/test_assistente.py; fixtures de tests/mcp/test_servidor.py (AGORA = 08/10/2026 15:00 BRT)."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, rpc  # noqa: F401  (fixtures e helpers)


@pytest.fixture
def cli_tok(banco):
    c = conectar(banco)
    tok = {"fin": emitir(c, "fin", ["fin"]), "so_trab": emitir(c, "so-trab", ["trabalho"])}
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        yield cli, tok


def _chamar(cli, token, ferramenta, **args):
    r = rpc(cli, token, "tools/call", {"name": ferramenta, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return json.loads(res["content"][0]["text"]) if res.get("content") else res


def test_escopo_fin_e_so_os_sinais_financeiros(cli_tok):
    cli, tok = cli_tok
    assert ESCOPOS_FERRAMENTAS["olhar_a_frente"] == "fin"
    f = _chamar(cli, tok["fin"], "olhar_a_frente")
    assert f["dados"]["ha_alerta"] in (True, False) and set(f["dados"]) == {"dias", "caixa", "a_receber_atrasado", "ha_alerta"}
    assert _chamar(cli, tok["so_trab"], "olhar_a_frente")["erro"] == "sem_escopo"


def test_dias_fora_de_7_a_90_sao_recusados(cli_tok):
    cli, tok = cli_tok
    for dias in (0, 91):
        assert "erro" in _chamar(cli, tok["fin"], "olhar_a_frente", dias=dias)
    assert _chamar(cli, tok["fin"], "olhar_a_frente", dias=7)["dados"]["dias"] == 7
