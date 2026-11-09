"""revisao_semana (ADR-037): o que andou e o que parou em 7 dias. Só lê tabelas locais. AGORA = 09/11/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import antecipar, revisao
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _ativ(con, texto, status="aberta", vence=None, criada="2026-11-01T00:00:00+00:00", concluida=None):
    con.execute("insert into atividade(texto, vence_em, status, origem, criada_em, concluida_em) values (?,?,?,?,?,?)",
                (texto, vence, status, "hermes", criada, concluida))


def test_banco_vazio(con):
    r = revisao.revisao_semana(con, AGORA)
    assert r["atividades"] == {"concluidas": [], "vencidas": [], "sem_data_antigas": []}
    assert r["projetos_parados"] == [] and r["decisoes_antigas"] == [] and r["documentos"] == []
    assert r["caixa"] == {"hoje_centavos": 0, "ha_7_dias_centavos": 0, "variacao_centavos": 0}


def test_atividades_concluidas_vencidas_e_sem_data_antigas(con):
    _ativ(con, "feita ontem", "feita", concluida="2026-11-08T12:00:00+00:00")
    _ativ(con, "feita faz tempo", "feita", concluida="2026-10-01T12:00:00+00:00")
    _ativ(con, "vencida", vence="2026-11-05T03:00:00+00:00")
    _ativ(con, "sem data velha", criada="2026-10-01T00:00:00+00:00")
    _ativ(con, "sem data nova", criada="2026-11-08T00:00:00+00:00")
    a = revisao.revisao_semana(con, AGORA)["atividades"]
    assert [x["texto"] for x in a["concluidas"]] == ["feita ontem"]
    assert [x["texto"] for x in a["vencidas"]] == ["vencida"]
    assert [x["texto"] for x in a["sem_data_antigas"]] == ["sem data velha"]


def test_decisoes_abertas_ha_mais_de_7_dias(con):
    for titulo, criada in (("velha", "2026-10-30T00:00:00+00:00"), ("nova", "2026-11-08T00:00:00+00:00")):
        con.execute("insert into pergunta(tipo, titulo, opcoes, estado, criada_em) values ('x', ?, '[]', 'aberta', ?)", (titulo, criada))
    assert [d["titulo"] for d in revisao.revisao_semana(con, AGORA)["decisoes_antigas"]] == ["velha"]


def test_variacao_do_caixa(con):
    con.execute("insert into conta(id, apelido, tipo, estado, externo_id) values (1,'itau','BANK','sim','x')")
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (1,'2026-11-01T10:00:00',100000), (1,'2026-11-09T10:00:00',40000)")
    assert revisao.revisao_semana(con, AGORA)["caixa"] == {"hoje_centavos": 400_00, "ha_7_dias_centavos": 1000_00, "variacao_centavos": -600_00}


def test_documentos_vem_do_olhar_a_frente(con, monkeypatch):
    monkeypatch.setattr(antecipar.repositorio, "vencimentos", lambda con, hoje, meses: [
        {"documento_id": 1, "titular_nome": "Louise", "tipo": "passaporte", "data": "2026-11-20", "vencido": False}])
    assert [d["documento_id"] for d in revisao.revisao_semana(con, AGORA)["documentos"]] == [1]
