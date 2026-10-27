"""Projetos (ADR-034): criar com atividades e dependências, listar, atualizar, resolver. Consome: gabi.projetos, gabi.atividades. AGORA = 27/10/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import atividades, projetos
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _criar(con, nome="Carro", atividades_=None, **kw):
    return projetos.criar(con, AGORA, "hermes", "hermes", nome, atividades=atividades_, **kw)


def _tres(con):
    return _criar(con, atividades_=[{"texto": "pedir orçamento"}, {"texto": "aprovar serviço", "depois_de": 1}, {"texto": "buscar o carro", "marco": True}])


def _ativs(con, projeto_id):
    return {a["texto"]: a for a in atividades.listar(con, AGORA, projeto_id=projeto_id)}


def test_criar_projeto_com_atividades_e_dependencias(con):
    p = _tres(con)
    a = _ativs(con, p["id"])
    assert a["pedir orçamento"]["bloqueada"] is False
    assert a["aprovar serviço"]["bloqueada"] is True and a["aprovar serviço"]["depende_de_id"] == a["pedir orçamento"]["id"]
    assert a["buscar o carro"]["marco"] is True and a["buscar o carro"]["bloqueada"] is False
    assert p["status"] == "ativo" and p["progresso"] == {"feitas": 0, "total": 3}
    assert con.execute("select count(*) from decisao").fetchone()[0] == 1


@pytest.mark.parametrize("depois_de", [2, 3, 0, 99, -1])
def test_ciclo_ou_indice_invalido_recusa_tudo_e_nao_grava(con, depois_de):
    with pytest.raises(ValueError):
        _criar(con, atividades_=[{"texto": "a"}, {"texto": "b", "depois_de": depois_de}])
    assert con.execute("select count(*) from projeto").fetchone()[0] == 0
    assert con.execute("select count(*) from atividade").fetchone()[0] == 0
    assert con.execute("select count(*) from decisao").fetchone()[0] == 0


def test_mais_de_30_atividades_recusado(con):
    with pytest.raises(ValueError):
        _criar(con, atividades_=[{"texto": f"t{i}"} for i in range(31)])
    assert _criar(con, nome="Outro", atividades_=[{"texto": f"t{i}"} for i in range(30)])["progresso"]["total"] == 30


def test_concluir_a_primeira_libera_a_segunda(con):
    p = _tres(con)
    a = _ativs(con, p["id"])
    atividades.concluir(con, AGORA, "hermes", "hermes", a["pedir orçamento"]["id"])
    assert _ativs(con, p["id"])["aprovar serviço"]["bloqueada"] is False


def test_cancelar_a_primeira_tambem_libera(con):
    p = _tres(con)
    a = _ativs(con, p["id"])
    atividades.cancelar(con, AGORA, "hermes", "hermes", a["pedir orçamento"]["id"])
    assert _ativs(con, p["id"])["aprovar serviço"]["bloqueada"] is False


def test_projeto_encerrado_nao_aceita_atividade_nova_nem_reabre(con):
    p = _criar(con)
    r = projetos.atualizar(con, AGORA, "hermes", "hermes", p["id"], status="concluido")
    assert r["status"] == "concluido"
    assert con.execute("select encerrado_em from projeto where id=?", (p["id"],)).fetchone()[0] is not None
    with pytest.raises(ValueError):
        atividades.criar(con, AGORA, "hermes", "hermes", "nova", projeto_id=p["id"])
    with pytest.raises(ValueError):
        projetos.atualizar(con, AGORA, "hermes", "hermes", p["id"], status="ativo")


def test_cancelar_projeto_cancela_as_abertas_e_nao_deixa_bloqueada(con):
    p = _tres(con)
    projetos.atualizar(con, AGORA, "hermes", "hermes", p["id"], status="cancelado")
    assert atividades.listar(con, AGORA, projeto_id=p["id"]) == []


def test_listar_mostra_progresso(con):
    p = _tres(con)
    atividades.concluir(con, AGORA, "hermes", "hermes", _ativs(con, p["id"])["pedir orçamento"]["id"])
    item = projetos.listar(con, AGORA)[0]
    assert item["progresso"] == {"feitas": 1, "total": 3}
    assert projetos.listar(con, AGORA, status="pausado") == []


def test_resolver_por_id_e_por_trecho_sem_acento(con):
    a = _criar(con, nome="Reforma da Cozinha")
    _criar(con, nome="Carro")
    assert projetos.resolver(con, str(a["id"])) == a["id"]
    assert projetos.resolver(con, "cozinha") == a["id"]
    assert projetos.resolver(con, "COZINHÁ") == a["id"]


def test_resolver_ambiguo_e_inexistente(con):
    _criar(con, nome="Carro do Ricardo")
    _criar(con, nome="Carro da Louise")
    with pytest.raises(ValueError, match="Carro"):
        projetos.resolver(con, "carro")
    with pytest.raises(LookupError):
        projetos.resolver(con, "barco")


def test_atualizar_valor_prazo_e_nome(con):
    p = _criar(con)
    r = projetos.atualizar(con, AGORA, "painel", "painel", p["id"], prazo="2026-01-05", orcamento_centavos=300000, nome="Carro azul", objetivo="trocar o motor")
    assert (r["prazo"], r["nome"], r["objetivo"], r["orcamento_centavos"]) == ("2026-01-05", "Carro azul", "trocar o motor", 300000)
    with pytest.raises(ValueError):
        projetos.atualizar(con, AGORA, "painel", "painel", p["id"], prazo="amanhã")
    with pytest.raises(LookupError):
        projetos.atualizar(con, AGORA, "painel", "painel", 999, nome="x")
