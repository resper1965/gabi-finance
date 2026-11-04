import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.agenda.convites import pendentes, texto_aviso
from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?)", (json.dumps(["a@x.com"]),))
    return c


def _fonte(con, conta="a@x.com", estado="sim", cal="primary"):
    return con.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values (?,?,?,?)", (conta, "graph", cal, estado)).lastrowid


def _ev(con, fonte, ext, ini, fim, titulo="Reunião", resposta="needsAction", dia_inteiro=0, livre=0, org=None, serie=None):
    return con.execute(
        "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, livre, resposta, organizador_nome, serie_id)"
        " values (?,?,?,?,?,?,?,?,?,?,?,?)", (fonte, ext, ini, fim, ini[:10], fim[:10], dia_inteiro, titulo, livre, resposta, org, serie)).lastrowid


def test_pendente_so_needs_action_futuro(con):
    f = _fonte(con)
    ok = _ev(con, f, "1", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00", "Ok", org="Ana", serie="S1")
    _ev(con, f, "2", "2026-11-06T18:00:00+00:00", "2026-11-06T19:00:00+00:00", resposta="accepted")
    _ev(con, f, "3", "2026-11-03T18:00:00+00:00", "2026-11-03T19:00:00+00:00")
    _ev(con, f, "4", "2026-11-07T03:00:00+00:00", "2026-11-08T03:00:00+00:00", dia_inteiro=1)
    _ev(con, f, "5", "2026-11-09T18:00:00+00:00", "2026-11-09T19:00:00+00:00", resposta=None)
    r = pendentes(con, AGORA)
    assert r == [{"evento_id": ok, "conta": "a@x.com", "titulo": "Ok", "inicio_utc": "2026-11-05T18:00:00+00:00",
                  "fim_utc": "2026-11-05T19:00:00+00:00", "organizador_nome": "Ana", "serie_id": "S1", "conflita_com": []}]


def test_pendente_ignora_conta_fora_de_contas_agenda(con):
    f = _fonte(con, "b@x.com")
    _ev(con, f, "1", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00")
    f2 = _fonte(con, "a@x.com", estado="nao", cal="outro")
    _ev(con, f2, "2", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00")
    assert pendentes(con, AGORA) == []


def test_conflito_com_aceito_pendente_e_proprio(con):
    f = _fonte(con)
    _ev(con, f, "1", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00", "Convite")
    _ev(con, f, "2", "2026-11-05T18:30:00+00:00", "2026-11-05T19:30:00+00:00", "Aceito", resposta="accepted")
    _ev(con, f, "3", "2026-11-05T17:00:00+00:00", "2026-11-05T18:15:00+00:00", "Outro pendente")
    _ev(con, f, "4", "2026-11-05T18:10:00+00:00", "2026-11-05T18:20:00+00:00", "Meu", resposta=None)
    r = {i["titulo"]: i for i in pendentes(con, AGORA)}
    assert sorted(r["Convite"]["conflita_com"]) == ["Aceito", "Meu", "Outro pendente"]
    assert sorted(r["Outro pendente"]["conflita_com"]) == ["Convite", "Meu"]


def test_nao_conflita_livre_dia_inteiro_tentativo_nem_encostando(con):
    f = _fonte(con)
    _ev(con, f, "1", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00", "Convite")
    _ev(con, f, "2", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00", "Livre", resposta="accepted", livre=1)
    _ev(con, f, "3", "2026-11-05T03:00:00+00:00", "2026-11-06T03:00:00+00:00", "Dia", resposta="accepted", dia_inteiro=1)
    _ev(con, f, "4", "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00", "Talvez", resposta="tentative")
    _ev(con, f, "5", "2026-11-05T19:00:00+00:00", "2026-11-05T20:00:00+00:00", "Depois", resposta="accepted")
    _ev(con, f, "6", "2026-11-05T17:00:00+00:00", "2026-11-05T18:00:00+00:00", "Antes", resposta="accepted")
    assert pendentes(con, AGORA)[0]["conflita_com"] == []


def test_texto_aviso_com_e_sem_conflito_e_sem_organizador():
    base = {"titulo": "Sync", "inicio_utc": "2026-11-05T18:00:00+00:00", "fim_utc": "2026-11-05T19:00:00+00:00",
            "organizador_nome": "Ana", "conflita_com": ["Dentista"]}
    assert texto_aviso(base, "America/Sao_Paulo") == "Sync · qui 15h–16h · de Ana · conflita com Dentista"
    assert texto_aviso({**base, "conflita_com": []}, "America/Sao_Paulo") == "Sync · qui 15h–16h · de Ana · sem conflito"
    assert texto_aviso({**base, "organizador_nome": None, "inicio_utc": "2026-11-05T18:30:00+00:00"},
                       "America/Sao_Paulo") == "Sync · qui 15h30–16h · conflita com Dentista"
