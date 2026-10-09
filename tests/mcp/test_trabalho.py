import inspect

from gabi.mcp import ferramentas_trab, servidor
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS


def test_ferramentas_de_trabalho_tem_escopo_trabalho():
    assert {n for n, e in ESCOPOS_FERRAMENTAS.items() if e == "trabalho"} == {"hoje_resumo", "frentes_listar", "frentes_itens"}


def test_nenhuma_ferramenta_de_trabalho_envia_apaga_ou_confirma():
    nomes = [n for n in ferramentas_trab.ESCOPOS]
    assert not [n for n in nomes if any(p in n for p in ("enviar", "send", "apagar", "delete", "confirmar", "decidir"))]
    fonte = inspect.getsource(ferramentas_trab)
    assert "insert" not in fonte.lower() and "update " not in fonte.lower() and "delete" not in fonte.lower().replace("nenhuma ferramenta envia, apaga", "")
