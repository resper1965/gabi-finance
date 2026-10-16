import json
from pathlib import Path

import pytest

from gabi.agenda.sincronizar import sincronizar, sincronizar_fonte
from gabi.db import conectar, migrar
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.google_agenda import ResultadoEventos

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-12T12:00:00+00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com", cal="primary", estado="sim"):
    return con.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values (?,?,?,?)", (conta, "google", cal, estado)).lastrowid


def _ev(id_, ini="2026-10-13T13:00:00-03:00", fim="2026-10-13T14:00:00-03:00", titulo="Reunião", **kw):
    return {"externo_id": id_, "inicio": {"dateTime": ini}, "fim": {"dateTime": fim}, "titulo": titulo, "link_reuniao": None,
            "participantes_qtd": 2, "status": "confirmed", "etag": "e", "atualizado_origem": "2026-10-10T10:00:00Z", "privado": False, **kw}


class Falso:
    """Cliente falso: fila de respostas por chamada; registra os argumentos."""

    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, conta, calendario_id, sync_token, janela):
        self.chamadas.append((conta, calendario_id, sync_token, janela))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _ids(con):
    return sorted(r[0] for r in con.execute("select externo_id from agenda_evento"))


def test_carga_inicial_grava_eventos_e_token(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a"), _ev("b")], [], "T1", False))
    r = sincronizar_fonte(con, f, cli, AGORA)
    assert r == {"lidos": 2, "gravados": 2, "apagados": 0, "pulados": 0, "recarga": True}
    assert _ids(con) == ["a", "b"]
    row = con.execute("select * from agenda_fonte where id=?", (f,)).fetchone()
    assert row["sync_token"] == "T1" and row["sincronizada_em"] == AGORA and row["recarga_em"] == AGORA and row["ultimo_erro"] is None
    e = con.execute("select * from agenda_evento where externo_id='a'").fetchone()
    assert e["inicio_utc"] == "2026-10-13T16:00:00+00:00" and e["dia_local"] == "2026-10-13" and e["dia_inteiro"] == 0
    assert cli.chamadas[0][2] is None and set(cli.chamadas[0][3]) == {"de", "ate"}


def test_segunda_rodada_usa_o_token_e_aplica_so_mudancas(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a"), _ev("b")], [], "T1", False),
                ResultadoEventos([_ev("b", titulo="Novo")], [], "T2", False))
    sincronizar_fonte(con, f, cli, AGORA)
    r = sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert cli.chamadas[1][2] == "T1" and r["recarga"] is False and r["gravados"] == 1
    assert _ids(con) == ["a", "b"]
    assert con.execute("select titulo from agenda_evento where externo_id='b'").fetchone()[0] == "Novo"
    assert con.execute("select sync_token from agenda_fonte").fetchone()[0] == "T2"


def test_cancelado_e_apagado_inclusive_instancia_de_serie(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("serie_20261013"), _ev("serie_20261020"), _ev("x")], [], "T1", False),
                ResultadoEventos([], ["serie_20261020", "inexistente"], "T2", False))
    sincronizar_fonte(con, f, cli, AGORA)
    r = sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert _ids(con) == ["serie_20261013", "x"] and r["apagados"] == 1


def test_falha_na_segunda_pagina_nao_grava_nem_troca_o_token(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a")], [], "T1", False), ErroGoogleOAuth("calendar.events.list -> 500"))
    sincronizar_fonte(con, f, cli, AGORA)
    with pytest.raises(ErroGoogleOAuth):
        sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert _ids(con) == ["a"]
    assert con.execute("select sync_token, sincronizada_em from agenda_fonte").fetchone()[:] == ("T1", AGORA)


def test_410_recarrega_a_janela_e_apaga_o_que_sumiu(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a"), _ev("b"), _ev("c")], [], "T1", False),
                ResultadoEventos([_ev("a"), _ev("c")], [], "T9", True))
    sincronizar_fonte(con, f, cli, AGORA)
    r = sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert r["recarga"] is True and r["apagados"] == 1 and _ids(con) == ["a", "c"]
    assert con.execute("select sync_token from agenda_fonte").fetchone()[0] == "T9"


def test_recarga_semanal(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a"), _ev("b")], [], "T1", False), ResultadoEventos([_ev("a")], [], "T2", False),
                ResultadoEventos([_ev("a")], [], "T3", False))
    sincronizar_fonte(con, f, cli, AGORA)
    sincronizar_fonte(con, f, cli, "2026-10-18T12:00:00+00:00")  # 6 dias: incremental
    assert cli.chamadas[1][2] == "T1"
    r = sincronizar_fonte(con, f, cli, "2026-10-19T12:00:01+00:00")  # >7 dias desde a recarga: completa, sem token
    assert cli.chamadas[2][2] is None and r["recarga"] is True


def test_uma_fonte_falha_e_a_outra_sincroniza_e_linhas_antigas_ficam(con):
    f1, f2 = _fonte(con, "ruim@x.com"), _fonte(con, "boa@x.com")
    con.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (?,?,?,?,?,?,?)",
                (f1, "velho", "2026-10-13T16:00:00+00:00", "2026-10-13T17:00:00+00:00", "2026-10-13", "2026-10-13", "Velho"))

    def listar(conta, cal, tok, janela):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("calendar.events.list -> 500")
        return ResultadoEventos([_ev("n")], [], "T", False)
    r = sincronizar(con, listar, AGORA)
    assert r[f1] == {"erro": "calendar.events.list -> 500"} and r[f2]["gravados"] == 1
    assert _ids(con) == ["n", "velho"]
    assert con.execute("select ultimo_erro from agenda_fonte where id=?", (f1,)).fetchone()[0] == "calendar.events.list -> 500"


def test_fonte_desligada_nao_e_lida(con):
    _fonte(con, estado="nao"); _fonte(con, "b@x.com", estado="a_decidir")
    cli = Falso()
    assert sincronizar(con, cli, AGORA) == {} and cli.chamadas == []


def _avisos(con):
    return [json.loads(r["payload"]) for r in con.execute("select payload from aviso where tipo='agenda_reconectar' and entregue_em is null")]


def test_credencial_recusada_gera_um_aviso_por_dia_e_fecha_ao_voltar(con):
    _fonte(con, "a@x.com")
    erro = ErroGoogleOAuth("conta não autorizada: a@x.com")
    cli = Falso(erro, erro, ResultadoEventos([], [], "T", False))
    sincronizar(con, cli, AGORA)
    sincronizar(con, cli, "2026-10-12T12:15:00+00:00")
    assert len(_avisos(con)) == 1 and set(_avisos(con)[0]) == {"chave", "conta"} and _avisos(con)[0]["conta"] == "a@x.com"
    sincronizar(con, cli, "2026-10-12T12:30:00+00:00")
    assert _avisos(con) == []


def test_erro_comum_nao_gera_aviso_de_reconectar(con):
    _fonte(con)
    sincronizar(con, Falso(ErroGoogleOAuth("Google indisponível: timeout")), AGORA)
    assert _avisos(con) == []


def test_evento_com_data_invalida_e_pulado_e_contado(con):
    f = _fonte(con)
    ruim = _ev("ruim", ini="isto-nao-e-data", titulo="SEGREDO-TITULO")
    r = sincronizar_fonte(con, f, Falso(ResultadoEventos([ruim, _ev("ok")], [], "T", False)), AGORA)
    assert r["pulados"] == 1 and r["gravados"] == 1 and _ids(con) == ["ok"]


def test_privado_ocultar_mascara_o_titulo(con):
    f = _fonte(con)
    con.execute("insert into parametro(chave, valor) values ('agenda.privados', '\"ocultar\"')")
    sincronizar_fonte(con, f, Falso(ResultadoEventos([_ev("p", titulo="Médico", privado=True), _ev("q", titulo="Aberto")], [], "T", False)), AGORA)
    t = dict(con.execute("select externo_id, titulo from agenda_evento").fetchall())
    assert t == {"p": "Compromisso privado", "q": "Aberto"}
    assert con.execute("select privado from agenda_evento where externo_id='p'").fetchone()[0] == 1


def test_privado_por_padrao_mostra_o_titulo(con):
    f = _fonte(con)
    sincronizar_fonte(con, f, Falso(ResultadoEventos([_ev("p", titulo="Médico", privado=True)], [], "T", False)), AGORA)
    assert con.execute("select titulo from agenda_evento").fetchone()[0] == "Médico"


def test_sincronizacao_idempotente(con):
    f = _fonte(con)
    res = lambda: ResultadoEventos([_ev("a"), _ev("b")], [], "T1", False)
    cli = Falso(res(), res())
    sincronizar_fonte(con, f, cli, AGORA)
    antes = [tuple(r) for r in con.execute("select * from agenda_evento order by id")]
    sincronizar_fonte(con, f, cli, AGORA)
    assert [tuple(r) for r in con.execute("select * from agenda_evento order by id")] == antes


def test_excecao_qualquer_numa_fonte_nao_derruba_as_outras_nem_vaza_texto(con):
    a = _fonte(con, "a@x.com"); b = _fonte(con, "b@x.com")
    cli = Falso(RuntimeError("segredo do titulo"), ResultadoEventos([_ev("e1")], [], "T", False))
    saida = sincronizar(con, cli, AGORA)
    assert saida[a] == {"erro": "RuntimeError"} and saida[b]["gravados"] == 1
    assert con.execute("select ultimo_erro from agenda_fonte where id=?", (a,)).fetchone()[0] == "RuntimeError"
    assert _avisos(con) == []


def test_parametro_de_janela_corrompido_usa_o_padrao(con):
    f = _fonte(con)
    con.execute("insert into parametro(chave, valor) values ('agenda.janela_passado_dias', '\"abc\"'), ('agenda.janela_futuro_dias', '[1]')")
    cli = Falso(ResultadoEventos([_ev("e1")], [], "T", False))
    assert sincronizar_fonte(con, f, cli, AGORA)["gravados"] == 1


def test_recarga_vazia_nao_apaga_o_que_ja_existe(con):
    f = _fonte(con)
    sincronizar_fonte(con, f, Falso(ResultadoEventos([_ev("e1"), _ev("e2")], [], "T", False)), AGORA)
    r = sincronizar_fonte(con, f, Falso(ResultadoEventos([], [], None, True)), "2026-10-12T12:15:00+00:00")
    assert _ids(con) == ["e1", "e2"] and r["apagados"] == 0
    assert "vazia" in con.execute("select ultimo_erro from agenda_fonte where id=?", (f,)).fetchone()[0]


def test_403_sem_motivo_so_avisa_na_segunda_falha_seguida(con):
    _fonte(con)
    cli = Falso(*[ErroGoogleOAuth("calendar.events.list -> 403")] * 3, ResultadoEventos([], [], "T", False))
    sincronizar(con, cli, AGORA)
    assert _avisos(con) == []
    sincronizar(con, cli, "2026-10-12T12:15:00+00:00")
    assert len(_avisos(con)) == 1


def test_400_nao_e_credencial(con):
    _fonte(con)
    sincronizar(con, Falso(ErroGoogleOAuth("calendar.events.list -> 400")), AGORA)
    assert _avisos(con) == []


def test_grava_ical_uid_e_livre_e_atualiza_na_mudanca(con):
    f = _fonte(con)
    cli = Falso(ResultadoEventos([_ev("a", ical_uid="u@google.com", livre=True)], [], "T1", False),
                ResultadoEventos([_ev("a", ical_uid="u@google.com", livre=False)], [], "T2", False))
    sincronizar_fonte(con, f, cli, AGORA)
    r = con.execute("select ical_uid, livre from agenda_evento where externo_id='a'").fetchone()
    assert (r["ical_uid"], r["livre"]) == ("u@google.com", 1)
    sincronizar_fonte(con, f, cli, AGORA)
    assert con.execute("select livre from agenda_evento where externo_id='a'").fetchone()[0] == 0


def test_auth_delegacao_sem_cliente_nao_chama_o_google(con):
    """Agenda M9: auth=delegacao ainda não tem cliente; a fonte devolve erro claro e o cliente OAuth nunca é chamado."""
    f = con.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado, auth) values ('a@x.com','google','primary','sim','delegacao')").lastrowid
    cli = Falso()
    assert sincronizar(con, cli, AGORA) == {f: {"erro": "autenticação por delegação sem cliente ainda"}}
    assert cli.chamadas == []
