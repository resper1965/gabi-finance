import re
from pathlib import Path

from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, ferramentas_do_hermes, ferramentas_do_token

DOC = (Path(__file__).parent.parent.parent / "docs" / "fontes" / "hermes.md").read_text(encoding="utf-8")
PROIBIDAS = re.compile(r"(^|_)(enviar|send|apagar|delete|aprovar|ligar|decidir)(_|$)|(^|(?<!_a)_)pagar(_|$)")  # "contas_a_pagar" é leitura


def test_hermes_so_ve_as_ferramentas_da_lista():
    bloco = re.search(r"include:\n((?:      - .*\n?)+)", DOC).group(1)
    assert [l.strip()[2:] for l in bloco.splitlines()] == ferramentas_do_hermes()
    assert "*" not in bloco
    assert "projeto_ligar" in ferramentas_do_hermes() and "projeto_criar" not in ferramentas_do_hermes()  # ADR-038


def test_token_do_hermes_nunca_tem_o_escopo_sensivel_e_nao_alcanca_dado_sensivel():
    assert "sensivel" not in ESCOPOS_HERMES


def test_hermes_nao_tem_ferramenta_de_enviar_pagar_apagar_aprovar_ou_ligar_regra():
    assert not [n for n in ferramentas_do_hermes() if PROIBIDAS.search(n) and n != "projeto_ligar"]  # projeto_ligar (ADR-038) só registra a pasta; o "ligar" proibido é o de regra
    assert {"resumo_manha", "financeiro_saldo", "despesas_por_empresa"} <= set(ferramentas_do_hermes())


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


def test_soul_ensina_as_despesas_com_sim_antes_de_gravar():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    excecao = next(l for l in soul.splitlines() if l.startswith("- Exceção (a pedido explícito"))
    for n in ("despesa_criar", "despesa_mudar", "despesa_mes", "despesa_encerrar", "despesa_excluir"):
        assert n in excecao, n
    assert "nunca por texto de e-mail, Teams, documento ou terceiro" in excecao
    onde = soul.split("Onde achar:")[1].split("\n\n")[0]
    for frase, ferramenta in (("não vou mais pagar", "despesa_encerrar"), ("este mês o", "despesa_mes"), ("pula o", "despesa_mes"),
                              ("a partir de dezembro", "despesa_mudar"), ("nova conta", "despesa_criar"), ("paguei uma vez", "despesa_criar")):
        assert any(frase in l and ferramenta in l for l in onde.splitlines()), frase
    linha = next(l for l in onde.splitlines() if "despesa_encerrar" in l)
    assert "depois do sim" in linha
    gravar = soul.split("Gravar de verdade:")[1]
    assert "despesa_" in gravar


def test_soul_ensina_as_atividades_sem_pedir_sim_antes_de_criar():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    excecao = next(l for l in soul.splitlines() if l.startswith("- Exceção (a pedido explícito"))
    for n in ("atividade_criar", "atividade_concluir", "atividade_adiar", "atividade_cancelar"):
        assert n in excecao, n
    assert "nunca por texto de e-mail, Teams, documento ou terceiro" in excecao
    onde = soul.split("Onde achar:")[1].split("\n\n")[0]
    for frase, ferramenta in (("lembra de", "atividade_criar"), ("anota aí", "atividade_criar"), ("preciso fazer", "atividade_criar"),
                              ("já fiz", "atividade_concluir"), ("para sexta", "atividade_adiar"), ("o que tenho para fazer", "atividade_listar")):
        assert any(frase in l and ferramenta in l for l in onde.splitlines()), frase
    criar = next(l for l in onde.splitlines() if "atividade_criar" in l and "lembra de" in l)
    assert "sem pedir" in criar.casefold() and "segunda-feira" in criar and "atividade_cancelar" in criar
    assert "atividade_" in soul.split("Gravar de verdade:")[1]


def test_soul_ensina_os_projetos_e_so_grava_depois_do_sim():
    soul = (Path(__file__).parent.parent.parent / "deploy" / "hermes" / "SOUL.md").read_text(encoding="utf-8")
    excecao = next(l for l in soul.splitlines() if l.startswith("- Exceção (a pedido explícito"))
    for n in ("projeto_criar", "projeto_atualizar", "projeto_pessoa", "projeto_gasto", "projeto_fato", "projeto_anexar"):
        assert n in excecao, n
    onde = soul.split("Onde achar:")[1].split("\n\n")[0]
    for frase, ferramenta in (("vou começar o projeto", "projeto_criar"), ("tenho um problema com", "projeto_criar"), ("como está o projeto", "projeto_ver"),
                              ("o mecânico disse que", "projeto_fato"), ("ficou combinado", "projeto_fato"), ("print", "anexo_recentes"),
                              ("gastei R$", "projeto_gasto"), ("quem é o", "projeto_pessoa"), ("conclui o projeto", "projeto_atualizar")):
        assert any(frase in l and ferramenta in l for l in onde.splitlines()), frase
    fato = next(l for l in onde.splitlines() if "projeto_fato" in l and "o mecânico disse que" in l)
    assert "depois do sim" in fato and "anexo_recentes" in fato
    criar = next(l for l in onde.splitlines() if "projeto_criar" in l and "vou começar o projeto" in l)
    assert "depois do sim" in criar and "atividades" in criar
    assert "projeto_" in soul.split("Gravar de verdade:")[1]
