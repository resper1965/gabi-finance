import re
from pathlib import Path

from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, ferramentas_do_token

DOC = (Path(__file__).parent.parent.parent / "docs" / "fontes" / "hermes.md").read_text(encoding="utf-8")
PROIBIDAS = re.compile(r"(^|_)(enviar|send|apagar|delete|aprovar|ligar|decidir)(_|$)|(^|(?<!_a)_)pagar(_|$)")  # "contas_a_pagar" é leitura


def test_hermes_so_ve_as_ferramentas_da_lista():
    bloco = re.search(r"include:\n((?:      - .*\n?)+)", DOC).group(1)
    assert [l.strip()[2:] for l in bloco.splitlines()] == ferramentas_do_token(ESCOPOS_HERMES)
    assert "*" not in bloco


def test_token_do_hermes_nunca_tem_o_escopo_sensivel_e_nao_alcanca_dado_sensivel():
    assert "sensivel" not in ESCOPOS_HERMES


def test_hermes_nao_tem_ferramenta_de_enviar_pagar_apagar_aprovar_ou_ligar_regra():
    assert not [n for n in ferramentas_do_token(ESCOPOS_HERMES) if PROIBIDAS.search(n)]
    assert {"avisos_pendentes", "avisos_confirmar_entrega", "resumo_manha", "financeiro_saldo"} <= set(ferramentas_do_token(ESCOPOS_HERMES))


def test_toda_ferramenta_tem_escopo_conhecido():
    assert set(ESCOPOS_FERRAMENTAS.values()) <= set(ESCOPOS_HERMES) | {"sensivel"}


def test_token_sem_escopo_ve_lista_vazia():
    assert ferramentas_do_token([]) == []
