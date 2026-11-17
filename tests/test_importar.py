import json
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
        "pessoa": 2, "empresa": 1, "compromisso_fixo": 1, "matriz_acesso": 2,
        "compromisso": 3, "agenda_estado": 1, "agenda_eventos": 1, "conciliacao": 1, "fatura": 1,
        "conta_estado": 1, "compromisso_linha": 0, "valor_do_mes": 0, "parametro": 0}


def test_pets_allowlist_e_memoria_do_staging_sao_ignorados(con):
    """O staging da fixture ainda traz pets, allowlist_vip e memoria.jsonl; o carregador não os lê (as tabelas caíram na 0091)."""
    importar_staging(con, STAGING)
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert not {"pet", "allowlist_vip", "memoria"} & nomes


def test_importar_duas_vezes_nao_duplica(con):
    primeira = importar_staging(con, STAGING)
    assert importar_staging(con, STAGING) == primeira


def test_preserva_acentos_e_aspas(con):
    importar_staging(con, STAGING)
    assert con.execute("select nome from pessoa where id='p1'").fetchone()[0] == "João da Conceição"
    assert con.execute("select nome from empresa").fetchone()[0] == 'Empresa "Exemplo"'


def test_dinheiro_vira_centavos_inteiros(con):
    importar_staging(con, STAGING)
    assert con.execute("select valor_centavos from compromisso where id='aluguel:2026-10'").fetchone()[0] == 10150
    assert con.execute("select total_centavos, minimo_centavos from fatura").fetchone()[:] == (50025, 5000)
    assert con.execute("select saldo_centavos from conta_estado").fetchone()[0] == 123456
    assert con.execute("select typeof(saldo_centavos) from conta_estado").fetchone()[0] == "integer"


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


def test_id_de_compromisso_e_texto_como_no_gabi_fin(con):
    importar_staging(con, STAGING)
    ids = sorted(r[0] for r in con.execute("select id from compromisso"))
    assert ids == ["aluguel:2026-10", "energia:2026-10", "iptu:2026-10"]
    assert con.execute("select typeof(id) from compromisso limit 1").fetchone()[0] == "text"
    assert con.execute("select compromisso_id from conciliacao").fetchone()[0] == "aluguel:2026-10"


# ---------------- Cadastros de compromissos (snapshot da planilha) ----------------
def _staging_com_planilha(tmp_path):
    from tools.golden import _bruto_planilha
    d = tmp_path / "staging"
    shutil.copytree(STAGING, d)
    fin = json.loads((d / "fin.json").read_text(encoding="utf-8"))
    fin["planilha"] = {"lida_em": "2026-10-07T14:26:31-03:00", "conteudo": _bruto_planilha()}
    (d / "fin.json").write_text(json.dumps(fin, ensure_ascii=False), encoding="utf-8")
    return d


def test_semeia_os_cadastros_a_partir_do_snapshot_da_planilha(con, tmp_path):
    rel = {}
    n = importar_staging(con, _staging_com_planilha(tmp_path), relatorio=rel)
    assert n["compromisso_linha"] == 3 and n["valor_do_mes"] == 2          # as 3 linhas válidas e os 2 valores válidos
    assert n["parametro"] >= 6
    assert {r[0] for r in con.execute("select id from compromisso_linha")} == {"aluguel", "energia", "escola"}
    assert con.execute("select valor_padrao_centavos from compromisso_linha where id='aluguel'").fetchone()[0] == 200000
    assert len(rel["cadastros_invalidas"]) == 12 and rel["cadastros_semeados"] is True


def test_nao_sobrescreve_cadastros_ja_editados_no_painel(con, tmp_path):
    d = _staging_com_planilha(tmp_path)
    importar_staging(con, d)
    con.execute("update compromisso_linha set valor_padrao_centavos=999 where id='aluguel'")  # edição do Ricardo
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('novo','Novo','NOVO','dia:3')")
    rel = {}
    importar_staging(con, d, relatorio=rel)
    assert rel["cadastros_semeados"] is False
    assert con.execute("select valor_padrao_centavos from compromisso_linha where id='aluguel'").fetchone()[0] == 999
    assert con.execute("select count(*) from compromisso_linha where id='novo'").fetchone()[0] == 1


def test_staging_sem_planilha_nao_semeia_e_nao_quebra(con):
    rel = {}
    n = importar_staging(con, STAGING, relatorio=rel)
    assert n["compromisso_linha"] == 0 and rel["cadastros_semeados"] is False


def test_apelidos_e_params_voltam_certos_depois_de_semear(con, tmp_path):
    from gabi.dinheiro.repositorio import ler_leitura
    importar_staging(con, _staging_com_planilha(tmp_path))
    L = ler_leitura(con)
    assert next(l for l in L["linhas"] if l["id"] == "aluguel")["apelidos"] == ["IMOB SUL", "ALUGUEL"]
    assert L["params"]["janela_antes_dias"] == 7 and L["params"]["tolerancia_fixo"] == 0.02
    assert L["params"]["bancos_pj"] == {"C6 PJ", "Inter PJ"} and L["params"]["horas_conta_parada"] == 24
