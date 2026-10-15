import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.agenda import consulta
from gabi.db import conectar, migrar
from gabi.mcp.ferramentas_trab import agenda_listar, resumo_da_manha
from gabi.trabalho import hoje as modulo_hoje

MIGR = Path(__file__).parent.parent.parent / "migrations"
BRT = "America/Sao_Paulo"
AGORA = dt.datetime(2026, 10, 12, 10, 0, tzinfo=dt.timezone.utc)  # 07:00 BRT, segunda


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com", estado="sim"):
    return con.execute("insert into agenda_fonte(conta, provedor, estado) values (?, 'google', ?)", (conta, estado)).lastrowid


def _ev(con, fonte, ext, ini, fim, titulo="Reunião", inteiro=False, privado=False, link=None):
    """ini/fim: ISO com offset (horário) ou 'AAAA-MM-DD' (dia inteiro, fim exclusivo)."""
    from gabi.agenda import tempo
    j = (tempo.de_google({"date": ini}, {"date": fim}, BRT) if inteiro else tempo.de_google({"dateTime": ini}, {"dateTime": fim}, BRT))
    return con.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, link_reuniao, privado)"
                       " values (?,?,?,?,?,?,?,?,?,?)", (fonte, ext, j.inicio_utc, j.fim_utc, j.dia_local, j.dia_fim_local, int(inteiro), titulo, link, int(privado))).lastrowid


def test_evento_das_22h_aparece_no_dia_certo(con):
    f = _fonte(con)
    _ev(con, f, "x", "2026-10-12T22:30:00-03:00", "2026-10-12T23:30:00-03:00", "Jantar")  # 01:30Z do dia 13
    assert [e["titulo"] for e in consulta.agenda_do_dia(con, "2026-10-12", BRT)] == ["Jantar"]
    assert consulta.agenda_do_dia(con, "2026-10-13", BRT) == []
    assert consulta.agenda_do_dia(con, "2026-10-12", BRT)[0]["inicio_local"] == "2026-10-12T22:30:00-03:00"


def test_evento_que_cruza_a_meia_noite_aparece_nos_dois_dias(con):
    f = _fonte(con)
    _ev(con, f, "x", "2026-10-12T23:00:00-03:00", "2026-10-13T01:00:00-03:00", "Plantão")
    assert [e["titulo"] for e in consulta.agenda_do_dia(con, "2026-10-12", BRT)] == ["Plantão"]
    assert [e["titulo"] for e in consulta.agenda_do_dia(con, "2026-10-13", BRT)] == ["Plantão"]
    assert consulta.agenda_do_dia(con, "2026-10-14", BRT) == []


def test_dia_inteiro_sem_horario_e_nunca_conflita(con):
    f = _fonte(con)
    _ev(con, f, "d", "2026-10-12", "2026-10-13", "Feriado", inteiro=True)
    _ev(con, f, "a", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "A")
    item = consulta.agenda_do_dia(con, "2026-10-12", BRT)[0]
    assert item["titulo"] == "Feriado" and item["dia_inteiro"] is True and item["inicio_local"] is None and item["fim_local"] is None
    assert consulta.conflitos(con, "2026-10-12", "2026-10-12") == []


def test_conflito_por_instante_e_encostar_nao_conflita(con):
    f = _fonte(con)
    a = _ev(con, f, "a", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "A")
    b = _ev(con, f, "b", "2026-10-12T10:30:00-03:00", "2026-10-12T11:30:00-03:00", "B")
    _ev(con, f, "c", "2026-10-12T11:30:00-03:00", "2026-10-12T12:00:00-03:00", "C")  # encosta em B
    r = consulta.conflitos(con, "2026-10-12", "2026-10-12")
    assert [(c.evento_a, c.evento_b, c.sugestao_inicio) for c in r] == [(a, b, "2026-10-12T11:30:00-03:00")]


def test_mesmo_evento_em_duas_contas_aparece_uma_vez_no_resumo_e_nos_conflitos(con):
    f1, f2 = _fonte(con, "a@x.com"), _fonte(con, "b@x.com")
    _ev(con, f1, "1", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "Reunião IONIC")
    _ev(con, f2, "9", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "  reunião   ionic ")  # mesma reunião, outra conta
    assert len(consulta.agenda_do_dia(con, "2026-10-12", BRT)) == 1
    assert consulta.conflitos(con, "2026-10-12", "2026-10-12") == []
    assert "📅 *Agenda* (1)" in resumo_da_manha(con, AGORA)["linhas"]


def test_fonte_desligada_nao_aparece(con):
    _ev(con, _fonte(con, estado="nao"), "x", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00")
    assert consulta.agenda_do_dia(con, "2026-10-12", BRT) == []


def test_resumo_da_manha_mostra_horario_local_e_dia_inteiro(con):
    f = _fonte(con)
    _ev(con, f, "d", "2026-10-12", "2026-10-13", "Viagem", inteiro=True)
    _ev(con, f, "a", "2026-10-12T14:00:00-03:00", "2026-10-12T15:00:00-03:00", "Reunião IONIC")
    _ev(con, f, "s", "2026-10-12T16:00:00-03:00", "2026-10-12T17:00:00-03:00", None)
    linhas = resumo_da_manha(con, AGORA)["linhas"]
    assert "📅 *Agenda* (3)" in linhas and "• Dia inteiro: Viagem" in linhas and "• 14:00 Reunião IONIC" in linhas  # 17:00Z mostrado como 14:00 de Brasília
    con.execute("update agenda_evento set titulo='' where externo_id='a'")
    assert "• 14:00 (sem título)" in resumo_da_manha(con, AGORA)["linhas"]


def test_privados_mostrar_so_painel_ocultar(con):
    f = _fonte(con)
    _ev(con, f, "p", "2026-10-12T09:00:00-03:00", "2026-10-12T10:00:00-03:00", "Psiquiatra", privado=True, link="https://meet/x")
    pega = lambda **k: consulta.agenda_do_dia(con, "2026-10-12", BRT, **k)[0]  # noqa: E731
    assert pega()["titulo"] == "Psiquiatra" and pega(painel=True)["privado"] is True  # padrão: mostrar
    con.execute("insert into parametro(chave, valor) values ('agenda.privados', ?)", (json.dumps("so_painel"),))
    assert pega(painel=True)["titulo"] == "Psiquiatra"
    fora = pega(painel=False)
    assert fora["titulo"] == "Compromisso privado" and fora["link_reuniao"] is None
    assert "Psiquiatra" not in resumo_da_manha(con, AGORA)["texto"]
    con.execute("update parametro set valor=? where chave='agenda.privados'", (json.dumps("ocultar"),))
    assert pega(painel=True)["titulo"] == "Compromisso privado"


def test_agenda_listar_respeita_limite_de_31_dias_e_escopo(con):
    from gabi.mcp import servidor
    assert servidor.ESCOPOS_FERRAMENTAS["agenda_listar"] == "trabalho"
    f = _fonte(con)
    _ev(con, f, "a", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "A")
    assert [e["titulo"] for e in agenda_listar(con, AGORA, "2026-10-12", "2026-10-12")["eventos"]] == ["A"]
    assert len(agenda_listar(con, AGORA, "2026-10-01", "2026-10-31")["eventos"]) == 1  # 31 dias: no limite
    for de, ate in (("2026-10-01", "2026-11-01"), ("2026-10-12", "2026-10-11"), ("ontem", "2026-10-12")):
        with pytest.raises(ValueError):
            agenda_listar(con, AGORA, de, ate)


def test_hoje_usa_agenda_evento(con):
    f = _fonte(con)
    _ev(con, f, "a", "2026-10-12T10:00:00-03:00", "2026-10-12T11:00:00-03:00", "A")
    _ev(con, f, "b", "2026-10-12T10:30:00-03:00", "2026-10-12T11:30:00-03:00", "B")
    d = modulo_hoje.hoje(con, AGORA)
    assert [e["titulo"] for e in d["agenda"]] == ["A", "B"] and any(p["tipo"] == "conflito" for p in d["prioridades"])
    assert modulo_hoje.hoje(con, AGORA, "e1")["agenda"] == []  # compromisso não tem empresa: a agenda só vai em 'all'
