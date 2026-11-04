"""Aviso `convite_agenda`: convite pendente vira um aviso, uma vez por horário. Consome: gabi.agenda.convites, gabi.avisos, rotas.avisos.descrever."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.avisos import RESOLVIDO, VALE, gerar_avisos, revalidar
from gabi.db import conectar, migrar
from gabi.rotas.avisos import descrever

MIGR = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
INI, FIM = "2026-11-05T18:00:00+00:00", "2026-11-05T19:00:00+00:00"  # qui 15h-16h em Brasília


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?)", (json.dumps(["a@x.com"]),))
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-11-04T11:00:00+00:00','2026-11-04T11:01:00+00:00','ok',1)")
    return c


def _ev(con, ini=INI, fim=FIM, resposta="needsAction", org="Ana", ext="1", serie=None):
    f = con.execute("select id from agenda_fonte").fetchone()
    f = f[0] if f else con.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values ('a@x.com','graph','primary','sim')").lastrowid
    return con.execute(
        "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, livre, resposta, organizador_nome, serie_id)"
        " values (?,?,?,?,?,?,0,'Alinhamento',0,?,?,?)", (f, ext, ini, fim, ini[:10], fim[:10], resposta, org, serie)).lastrowid


def _avisos(con):
    return [(r["id"], json.loads(r["payload"])) for r in con.execute("select id, payload from aviso where tipo='convite_agenda' order by id")]


def test_convite_pendente_gera_um_aviso_com_o_texto_da_spec(con):
    e = _ev(con)
    gerar_avisos(con, AGORA)
    [(_, p)] = _avisos(con)
    assert p == {"chave": f"{e}:{INI}", "evento_id": e, "conta": "a@x.com", "serie_id": None, "titulo": "Alinhamento", "inicio_utc": INI,
                 "texto": "Alinhamento · qui 15h–16h · de Ana · sem conflito"}
    assert descrever("convite_agenda", p) == ("Convite: Alinhamento", p["texto"] + " · painel › Envios")


def test_mesmo_convite_nao_avisa_de_novo_nem_no_dia_seguinte(con):
    _ev(con)
    gerar_avisos(con, AGORA)
    gerar_avisos(con, AGORA + dt.timedelta(hours=1))
    gerar_avisos(con, AGORA + dt.timedelta(days=1))
    assert len(_avisos(con)) == 1


def test_convite_com_horario_novo_avisa_de_novo(con):
    e = _ev(con)
    gerar_avisos(con, AGORA)
    con.execute("update agenda_evento set inicio_utc=?, fim_utc=?, dia_local=? where id=?", ("2026-11-06T18:00:00+00:00", "2026-11-06T19:00:00+00:00", "2026-11-06", e))
    gerar_avisos(con, AGORA + dt.timedelta(hours=1))
    assert [p["chave"] for _, p in _avisos(con)] == [f"{e}:{INI}", f"{e}:2026-11-06T18:00:00+00:00"]


def test_convite_respondido_fecha_o_aviso_aberto(con):
    e = _ev(con)
    gerar_avisos(con, AGORA)
    [(_, p)] = _avisos(con)
    assert revalidar(con, "convite_agenda", p)[0] == VALE
    con.execute("update agenda_evento set resposta='accepted' where id=?", (e,))
    assert revalidar(con, "convite_agenda", p)[0] == RESOLVIDO
    con.execute("update agenda_evento set resposta='needsAction', inicio_utc='2026-11-07T18:00:00+00:00' where id=?", (e,))
    assert revalidar(con, "convite_agenda", p)[0] == RESOLVIDO  # início mudou
    con.execute("delete from agenda_evento where id=?", (e,))
    assert revalidar(con, "convite_agenda", p)[0] == RESOLVIDO  # linha sumiu


def test_convite_organizado_por_ele_nao_gera_aviso(con):
    _ev(con, resposta="organizer")
    gerar_avisos(con, AGORA)
    assert _avisos(con) == []


def _diaria(con, n=10, serie="S1"):
    return [_ev(con, f"2026-11-{5 + d:02d}T18:00:00+00:00", f"2026-11-{5 + d:02d}T19:00:00+00:00", ext=f"{serie}-{d}", serie=serie) for d in range(n)]


def test_serie_gera_um_aviso_so_com_a_chave_da_serie(con):
    ids = _diaria(con)
    gerar_avisos(con, AGORA)
    [(_, p)] = _avisos(con)
    assert p["chave"] == "serie:S1" and p["evento_id"] == ids[0] and p["serie_id"] == "S1" and p["inicio_utc"] == INI
    # a ocorrência mostrada passa, a próxima vira a primeira: mesma série, nunca avisa de novo
    gerar_avisos(con, AGORA + dt.timedelta(days=1, hours=8))
    gerar_avisos(con, AGORA + dt.timedelta(days=3))
    assert len(_avisos(con)) == 1


def test_serie_remarcada_nao_avisa_de_novo_e_outra_serie_avisa(con):
    ids = _diaria(con, 3)
    gerar_avisos(con, AGORA)
    con.execute("update agenda_evento set inicio_utc='2026-11-05T20:00:00+00:00', fim_utc='2026-11-05T21:00:00+00:00' where id=?", (ids[0],))
    _diaria(con, 2, serie="S2")
    gerar_avisos(con, AGORA + dt.timedelta(hours=1))
    assert sorted(p["chave"] for _, p in _avisos(con)) == ["serie:S1", "serie:S2"]


def test_aviso_de_serie_vale_enquanto_a_serie_tiver_ocorrencia_sem_resposta(con):
    ids = _diaria(con, 3)
    gerar_avisos(con, AGORA)
    [(_, p)] = _avisos(con)
    con.execute("update agenda_evento set inicio_utc='2026-11-05T20:00:00+00:00' where id=?", (ids[0],))
    assert revalidar(con, "convite_agenda", p)[0] == VALE  # remarcar uma ocorrência não resolve a série
    con.execute("update agenda_evento set resposta='accepted' where serie_id='S1'")
    assert revalidar(con, "convite_agenda", p)[0] == RESOLVIDO  # respondida no Outlook
    con.execute("update agenda_evento set resposta='needsAction' where serie_id='S1'")
    con.execute("delete from agenda_evento where serie_id='S1'")
    assert revalidar(con, "convite_agenda", p)[0] == RESOLVIDO  # série apagada
