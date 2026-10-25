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
    assert {"resumo_manha", "financeiro_saldo", "despesas_por_empresa"} <= set(ferramentas_do_token(ESCOPOS_HERMES))


def test_toda_ferramenta_tem_escopo_conhecido():
    assert set(ESCOPOS_FERRAMENTAS.values()) <= set(ESCOPOS_HERMES) | {"sensivel"}


def test_token_sem_escopo_ve_lista_vazia():
    assert ferramentas_do_token([]) == []


def test_soul_ensina_a_gravar_de_verdade():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    assert "Gravar de verdade" in soul and "familia_registrar_pessoa" in soul and "familia_registrar_pet" in soul
    assert "Não tenho como gravar isso no brain; fica só nesta conversa." in soul


def test_soul_excecao_cobre_pessoa_pet_e_contato_sem_contradizer():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    excecao = next(l for l in soul.splitlines() if l.startswith("- Exceção:"))
    for n in ("familia_registrar_pessoa", "familia_registrar_pet", "familia_atualizar_contato", "familia_propor_documento"):
        assert n in excecao
    assert "pessoa, parentesco, apelido, nascimento, pet e contato da família" in excecao
    assert "(apelido, telefone" not in soul  # apelido não vai mais para familia_atualizar_contato
    regra = next(l for l in soul.splitlines() if "Você lê e propõe" in l)
    assert "fora a exceção abaixo" in regra


def test_soul_so_grava_fato_dito_e_nunca_cala():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    bloco = soul.split("Gravar de verdade:")[1].split("\n\n")[0]
    assert "Grave só o que o Ricardo afirma como fato" in bloco
    for termo in ("pergunta", "talvez", "acho que", "brincadeira", "terceiro", "você deduziu"):
        assert termo in bloco, termo
    assert "Quer que eu grave no brain: <fato>?" in bloco and "Não vou gravar isso no brain: <motivo curto>" in bloco
    assert "Nunca fique calado" in bloco
