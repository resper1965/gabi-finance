"""Avisos de atividades (ADR-033): na hora, no dia e resumo da manhã, pelo produtor `gerar_avisos`. Consome: gabi.atividades, gabi.avisos, rotas.avisos.descrever."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi import atividades
from gabi.avisos import RESOLVIDO, VALE, gerar_avisos, triar
from gabi.db import conectar, migrar
from gabi.rotas.avisos import descrever

UTC = dt.timezone.utc
CRIACAO = dt.datetime(2026, 10, 27, 9, 0, tzinfo=UTC)  # 06:00 em Brasília: tudo que vence hoje ainda é futuro
MIGR = Path(__file__).parent.parent / "migrations"


def utc(d, h, m=0):
    return dt.datetime(2026, 10, d, h, m, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _criar(con, texto, vence=None, agora=CRIACAO):
    return atividades.criar(con, agora, "hermes", "hermes", texto, vence)


def _avisos(con):
    return [(r["tipo"], json.loads(r["payload"])) for r in con.execute("select tipo, payload from aviso where tipo like 'atividade_%' order by id")]


def _tipos(con):
    return sorted(t for t, _ in _avisos(con))


def test_aviso_na_hora_so_depois_do_horario(con):
    _criar(con, "ligar pro contador", "2026-10-27T13:00")  # 16:00 UTC
    gerar_avisos(con, utc(27, 15))
    assert "atividade_hora" not in _tipos(con)
    gerar_avisos(con, utc(27, 16, 5))
    assert _tipos(con).count("atividade_hora") == 1
    gerar_avisos(con, utc(27, 16, 20))
    assert _tipos(con).count("atividade_hora") == 1


def test_hoje_e_resumo_so_depois_das_7h_brt(con):
    _criar(con, "pagar o IPTU", "2026-10-27")
    gerar_avisos(con, utc(27, 9, 59))  # 06:59 BRT
    assert _avisos(con) == []
    gerar_avisos(con, utc(27, 10, 1))  # 07:01 BRT
    assert _tipos(con) == ["atividade_hoje", "atividade_resumo"]


def test_resumo_vazio_nao_sai_e_grande_vira_e_mais_n(con):
    gerar_avisos(con, utc(27, 15))
    assert _avisos(con) == []
    for i in range(20):
        _criar(con, f"coisa {i:02d}")
    gerar_avisos(con, utc(27, 15))
    (tipo, p), = _avisos(con)
    assert tipo == "atividade_resumo" and p["total"] == 20 and len(p["sem_data"]) == 15
    titulo, texto = descrever(tipo, p)
    assert texto.endswith("e mais 5") and "json" not in texto and "{" not in texto


def test_resumo_separa_vencidas_hoje_e_sem_data(con):
    con.execute("insert into atividade(texto, vence_em, tem_hora, origem, criada_em) values ('atrasada','2026-10-26T12:00:00+00:00',0,'hermes','x')")
    _criar(con, "de hoje", "2026-10-27"); _criar(con, "solta"); _criar(con, "futura", "2026-11-05")
    gerar_avisos(con, utc(27, 15))
    p = dict(_avisos(con)).get("atividade_resumo")
    assert [i["texto"] for i in p["vencidas"]] == ["atrasada"] and [i["texto"] for i in p["hoje"]] == ["de hoje"]
    assert [i["texto"] for i in p["sem_data"]] == ["solta"] and p["total"] == 3


def test_virada_de_dia_brt(con):
    _criar(con, "reunião de fechamento", "2026-10-28T23:50")
    gerar_avisos(con, utc(29, 2, 30))  # 23:30 BRT de 28/10, mas já 29/10 em UTC
    p = dict(_avisos(con))["atividade_resumo"]
    assert [i["texto"] for i in p["hoje"]] == ["reunião de fechamento"] and p["vencidas"] == []


def test_concluir_antes_do_horario_nunca_envia(con):
    a = _criar(con, "ligar pro contador", "2026-10-27T13:00")
    gerar_avisos(con, utc(27, 16, 5))
    r = con.execute("select id, tipo, payload from aviso where tipo='atividade_hora'").fetchone()
    atividades.concluir(con, utc(27, 16, 6), "hermes", "hermes", a["id"])
    estado, _ = triar(con, r["id"], r["tipo"], json.loads(r["payload"]), utc(27, 16, 7))
    assert estado == RESOLVIDO
    f = con.execute("select telegram_em, entregue_em from aviso where id=?", (r["id"],)).fetchone()
    assert f["telegram_em"] == f["entregue_em"] is not None


def test_adiar_fecha_o_aviso_antigo_e_gera_outro(con):
    a = _criar(con, "ligar pro contador", "2026-10-27T13:00")
    gerar_avisos(con, utc(27, 16, 5))
    atividades.adiar(con, utc(27, 16, 6), "hermes", "hermes", a["id"], "2026-10-28T09:00")  # 12:00 UTC de 28/10
    gerar_avisos(con, utc(27, 16, 10))
    velho = con.execute("select telegram_em, entregue_em from aviso where tipo='atividade_hora'").fetchone()
    assert velho["telegram_em"] == velho["entregue_em"] is not None  # fechado sem enviar
    gerar_avisos(con, utc(28, 12, 5))
    horas = [r for r in con.execute("select entregue_em from aviso where tipo='atividade_hora' order by id")]
    assert len(horas) == 2 and horas[1]["entregue_em"] is None


def test_resumo_revalidado_na_entrega_e_vazio_resolve(con):
    a = _criar(con, "solta")
    gerar_avisos(con, utc(27, 15))
    r = con.execute("select id, tipo, payload from aviso where tipo='atividade_resumo'").fetchone()
    assert triar(con, r["id"], r["tipo"], json.loads(r["payload"]), utc(27, 15, 1))[0] == VALE
    atividades.concluir(con, utc(27, 15, 2), "hermes", "hermes", a["id"])
    assert triar(con, r["id"], r["tipo"], json.loads(r["payload"]), utc(27, 15, 3))[0] == RESOLVIDO


def test_descrever_pt_br(con):
    t, x = descrever("atividade_hora", {"id": 1, "texto": "ligar pro contador", "vence_em": "2026-10-27T13:00"})
    assert t == "Atividade agora: ligar pro contador" and "13:00" in x
    t, x = descrever("atividade_hoje", {"id": 1, "texto": "pagar o IPTU", "vence_em": "2026-10-27"})
    assert t == "Atividade para hoje: pagar o IPTU"
    t, x = descrever("atividade_resumo", {"vencidas": [{"id": 1, "texto": "a", "vence_em": "2026-10-26"}], "hoje": [{"id": 2, "texto": "b", "vence_em": "2026-10-27"}],
                                          "sem_data": [{"id": 3, "texto": "c", "vence_em": None}], "total": 3})
    assert t == "Atividades: 1 vencida, 1 para hoje, 1 sem data" and "a" in x and "b" in x and "c" in x


def test_aviso_na_hora_nao_repete_nos_dias_seguintes(con):
    _criar(con, "ligar pro contador", "2026-10-28T10:00")  # 13:00 UTC de 28/10
    for quando in (utc(28, 13, 5), utc(29, 0, 5), utc(29, 12), utc(30, 12)):
        gerar_avisos(con, quando)
    assert _tipos(con).count("atividade_hora") == 1


def test_criar_com_textos_so_de_emoji_nao_confunde_um_com_o_outro(con):
    a, b = _criar(con, "comprar 🍞"), _criar(con, "comprar 🥛")
    assert a["id"] != b["id"] and b["ja_existia"] is False
    assert [i["texto"] for i in atividades.abertas_por_texto(con, "🥛")] == ["comprar 🥛"]
    assert [i["texto"] for i in atividades.abertas_por_texto(con, "contadór")] == []
