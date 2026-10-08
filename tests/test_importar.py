import shutil
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.importar import importar_staging, main

MIGRACOES = Path(__file__).parent.parent / "migrations"
STAGING = Path(__file__).parent / "fixtures" / "staging"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_importa_contagens_da_fixture(con):
    n = importar_staging(con, STAGING)
    assert n == {
        "pessoa": 2, "pet": 1, "empresa": 1, "compromisso_fixo": 1, "matriz_acesso": 2, "allowlist_vip": 1,
        "compromisso": 3, "agenda_estado": 1, "agenda_eventos": 1, "conciliacao": 1, "fatura": 1,
        "conta_estado": 1, "memoria": 2}


def test_importar_duas_vezes_nao_duplica(con):
    primeira = importar_staging(con, STAGING)
    assert importar_staging(con, STAGING) == primeira


def test_preserva_acentos_e_aspas(con):
    importar_staging(con, STAGING)
    assert con.execute("select nome from pessoa where id='p1'").fetchone()[0] == "João da Conceição"
    assert con.execute("select nome from empresa").fetchone()[0] == 'Empresa "Exemplo"'


def test_dinheiro_vira_centavos_inteiros(con):
    importar_staging(con, STAGING)
    assert con.execute("select valor_centavos from compromisso where id=1").fetchone()[0] == 10150
    assert con.execute("select total_centavos, minimo_centavos from fatura").fetchone()[:] == (50025, 5000)
    assert con.execute("select saldo_centavos from conta_estado").fetchone()[0] == 123456
    assert con.execute("select typeof(saldo_centavos) from conta_estado").fetchone()[0] == "integer"


def test_memoria_busca_funciona_apos_importar(con):
    importar_staging(con, STAGING)
    achados = [r[0] for r in con.execute(
        "select m.texto from memoria_fts f join memoria m on m.id=f.rowid where memoria_fts match 'terca'")]
    assert achados == ["Consulta da Helena na terça"]


def test_compromisso_fixo_e_pessoa_referenciada(con):
    importar_staging(con, STAGING)
    linha = con.execute("select pessoa_id, valor_texto, dia_vencimento from compromisso_fixo").fetchone()
    assert tuple(linha) == ("p1", "R$ 1.000,00", 5)


def test_staging_incompleto_falha_sem_importar_nada(con, tmp_path):
    incompleto = tmp_path / "staging"
    shutil.copytree(STAGING, incompleto)
    (incompleto / "fin.json").unlink()
    with pytest.raises(FileNotFoundError):
        importar_staging(con, incompleto)
    assert con.execute("select count(*) from pessoa").fetchone()[0] == 0


def test_main_registra_rodada_ok(tmp_path):
    banco = tmp_path / "g.db"
    assert main(banco, STAGING) == 0
    con = conectar(banco)
    r = con.execute("select fonte, status, lidos from rodada").fetchone()
    assert (r["fonte"], r["status"]) == ("importacao-staging", "ok") and r["lidos"] > 0
    assert con.execute("select count(*) from pessoa").fetchone()[0] == 2
