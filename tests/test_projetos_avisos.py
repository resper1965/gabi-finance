"""Aviso `projeto_parado` (ADR-034): projeto ativo sem movimento há 7 dias, pelo produtor `gerar_avisos`. Consome: gabi.projetos, gabi.avisos, rotas.avisos.descrever."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi import atividades, projetos
from gabi.avisos import RESOLVIDO, VALE, gerar_avisos, triar
from gabi.db import conectar, migrar
from gabi.rotas.avisos import descrever

UTC = dt.timezone.utc
MIGR = Path(__file__).parent.parent / "migrations"
INICIO = dt.datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def em(dias, horas=0):
    return INICIO + dt.timedelta(days=dias, hours=horas)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _projeto(con, nome="Reforma", **kw):
    return projetos.criar(con, INICIO, "hermes", "hermes", nome, **kw)["id"]


def _avisos(con):
    return [(r["tipo"], json.loads(r["payload"])) for r in con.execute("select tipo, payload from aviso where tipo='projeto_parado' order by id")]


def test_projeto_sem_movimento_ha_7_dias_gera_aviso(con):
    p = _projeto(con)
    gerar_avisos(con, em(6, 23))
    assert _avisos(con) == []
    gerar_avisos(con, em(7))
    (tipo, payload), = _avisos(con)
    assert payload["id"] == p and payload["nome"] == "Reforma" and payload["parado_ha_dias"] == 7 and payload["chave"] == str(p)
    assert projetos.parados(con, em(7)) == [{"id": p, "nome": "Reforma", "parado_ha_dias": 7, "ultimo_em": INICIO.isoformat()}]


@pytest.mark.parametrize("movimento", ["atividade_criada", "atividade_concluida", "fato", "anexo"])
def test_atividade_fato_ou_anexo_recente_evita_o_aviso(con, movimento):
    p = _projeto(con, atividades=[{"texto": "antiga"}])
    antiga = atividades.listar(con, INICIO, projeto_id=p)[0]["id"]
    quando = em(5)
    if movimento == "atividade_criada":
        atividades.criar(con, quando, "hermes", "hermes", "nova", projeto_id=p)
    elif movimento == "atividade_concluida":
        atividades.concluir(con, quando, "hermes", "hermes", antiga)
    elif movimento == "fato":
        projetos.registrar_fato(con, quando, "hermes", "hermes", p, "o mecânico ligou")
    else:
        con.execute("insert into anexo(tipo, sha256, recebido_em, projeto_id) values ('imagem','a',?,?)", (quando.isoformat(), p))
    gerar_avisos(con, em(11))  # 6 dias depois do movimento
    assert _avisos(con) == []
    gerar_avisos(con, em(12))  # 7 dias
    assert len(_avisos(con)) == 1


def test_projeto_pausado_ou_encerrado_nao_avisa(con):
    a, b, c = _projeto(con, "A"), _projeto(con, "B"), _projeto(con, "C")
    projetos.atualizar(con, INICIO, "hermes", "hermes", a, status="pausado")
    projetos.atualizar(con, INICIO, "hermes", "hermes", b, status="concluido")
    gerar_avisos(con, em(30))
    assert [p["id"] for _, p in _avisos(con)] == [c]


def test_aviso_nao_repete_em_menos_de_7_dias_depois_de_lido(con):
    _projeto(con)
    gerar_avisos(con, em(8))
    assert len(_avisos(con)) == 1
    gerar_avisos(con, em(9))
    assert len(_avisos(con)) == 1  # aberto segura o novo
    con.execute("update aviso set entregue_em=? where tipo='projeto_parado'", (em(9).isoformat(),))
    gerar_avisos(con, em(12))
    assert len(_avisos(con)) == 1  # lido há 3 dias
    gerar_avisos(con, em(17))
    assert len(_avisos(con)) == 2


def test_movimento_depois_do_aviso_fecha_sem_enviar(con):
    p = _projeto(con)
    gerar_avisos(con, em(8))
    r = con.execute("select id, tipo, payload from aviso where tipo='projeto_parado'").fetchone()
    estado, _ = triar(con, r["id"], r["tipo"], json.loads(r["payload"]), em(8, 1))
    assert estado == VALE
    projetos.registrar_fato(con, em(8, 2), "hermes", "hermes", p, "mecânico respondeu")
    estado, _ = triar(con, r["id"], r["tipo"], json.loads(r["payload"]), em(8, 3))
    assert estado == RESOLVIDO
    f = con.execute("select telegram_em, entregue_em from aviso where id=?", (r["id"],)).fetchone()
    assert f["telegram_em"] == f["entregue_em"] is not None


def test_encerrar_o_projeto_depois_do_aviso_resolve(con):
    p = _projeto(con)
    gerar_avisos(con, em(8))
    r = con.execute("select id, tipo, payload from aviso where tipo='projeto_parado'").fetchone()
    projetos.atualizar(con, em(8, 1), "hermes", "hermes", p, status="cancelado")
    assert triar(con, r["id"], r["tipo"], json.loads(r["payload"]), em(8, 2))[0] == RESOLVIDO


def test_descrever_pt_br(con):
    _projeto(con, "Carro do Ricardo")
    gerar_avisos(con, em(9))
    (tipo, p), = _avisos(con)
    assert descrever(tipo, p) == ("Projeto parado: Carro do Ricardo", "sem movimento há 9 dias")
    assert descrever(tipo, {**p, "parado_ha_dias": 1})[1] == "sem movimento há 1 dia"
