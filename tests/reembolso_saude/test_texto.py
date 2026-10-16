import datetime as dt
import json

from gabi.reembolso_saude import texto
from gabi.rotas.avisos import descrever
from tests.reembolso_saude.conftest import AGORA, SEGREDOS, Modelo, arq, avisos, con, doc, dump_banco, pista, rodar, sistema  # noqa: F401

SEGUNDA_8H = dt.datetime(2026, 10, 19, 11, 0, tzinfo=dt.timezone.utc)   # segunda 08:00 em Brasília
SEGUNDA_7H = dt.datetime(2026, 10, 19, 10, 0, tzinfo=dt.timezone.utc)


def _dados(con, arq, extra=()):
    p, _ = sistema([doc(10, "nf1"), doc(11, "rec2", criado="2026-09-03", adicionado="2026-09-05T10:00:00-03:00"), doc(12, "baixa"), *extra])
    m = Modelo({"nf1": pista("nf"), "rec2": pista("recibo", prestador="Dr. Beto", data="2026-09-03"), "baixa": pista("nf", confianca=0.2, paciente="Teo")})
    rodar(con, arq, p, m)


def test_lista_de_segunda_sem_nomes_com_a_pedir_e_a_conferir(con, arq):
    _dados(con, arq)
    linhas = texto.montar_segunda(con, dt.date(2026, 10, 19))
    t = "\n".join(linhas)
    assert linhas[0] == "🩺 Reembolsos de saúde: segunda 19/10"
    assert "• Dossiê 1 (10/2026): falta comprovante · parado há 15 dias" in t
    assert "A conferir:" in t and "• Dossiê 3 (10/2026): documento 12" in t
    assert "Quem é cada dossiê: painel (Família) ou Paperless." in t
    assert not [s for s in SEGREDOS + ("Teo", "Beto") if s in t]


def test_lista_vazia_vira_uma_frase(con, arq):
    assert texto.montar_segunda(con, dt.date(2026, 10, 19)) == [texto.SEM_REEMBOLSO]


def test_dossie_pronto_aparece_como_pronto(con, arq):
    p, _ = sistema([doc(10, "nf1"), doc(11, "comp1")])
    rodar(con, arq, p, Modelo({"nf1": pista("nf"), "comp1": pista("comprovante")}))
    assert "• Dossiê 1 (10/2026): pronto para pedir · parado há 15 dias" in "\n".join(texto.montar_segunda(con, dt.date(2026, 10, 19)))


def test_aviso_da_semana_so_segunda_depois_das_8_e_uma_vez(con, arq):
    _dados(con, arq)
    assert texto.avisar_semana(con, AGORA) is None            # sexta
    assert texto.avisar_semana(con, SEGUNDA_7H) is None       # segunda, antes das 08h
    assert texto.avisar_semana(con, SEGUNDA_8H) is not None
    assert texto.avisar_semana(con, SEGUNDA_8H + dt.timedelta(hours=2)) is None
    (_, p), = avisos(con, "reembolso_saude_semana")
    assert p["chave"] == "2026-10-19" and "Dossiê 1" in "\n".join(p["linhas"])
    assert not [s for s in SEGREDOS if s in dump_banco(con)]


def test_aviso_da_semana_nao_sai_sem_reembolso(con, arq):
    assert texto.avisar_semana(con, SEGUNDA_8H) is None and avisos(con) == []


def test_descricao_dos_avisos_sem_nome():
    t, x = descrever("reembolso_saude_abre", {"dossie": 3, "mes": "2026-10", "faltam": ["comprovante", "CRM/CRP"]})
    assert t == "Reembolso a pedir: dossiê 3 (10/2026)" and x == "falta comprovante, CRM/CRP"
    assert descrever("reembolso_saude_pronto", {"dossie": 3, "mes": "2026-10", "faltam": []})[0] == "Reembolso pronto para pedir: dossiê 3 (10/2026)"
    t, x = descrever("reembolso_saude_sem_requisito", {"dossie": 3, "mes": "2026-10", "requisito": "nota fiscal"})
    assert t.startswith("Não é reembolsável: dossiê 3 (10/2026)") and "nota fiscal" in x
    t, x = descrever("reembolso_saude_semana", {"linhas": ["🩺 Reembolsos de saúde: segunda 19/10", "• Dossiê 1"]})
    assert t == "🩺 Reembolsos de saúde: segunda 19/10" and x == "• Dossiê 1"
    assert descrever("reembolso_saude_requisitos", {})[0] == "Requisitos do reembolso de saúde inválidos"
    assert descrever("reembolso_saude_sem_modelo", {"motivo": "teto"})[0] == "Reembolso de saúde sem modelo de leitura"
