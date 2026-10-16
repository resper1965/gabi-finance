import datetime as dt
import os
import stat

import pytest

from gabi.familia.saude import ChaveInvalida, abrir_saude, pode_ver, registrar_exame, resumo_para_consulta, serie
from gabi.identidade import Identidade

CHAVE = bytes(range(32))
OUTRA = bytes(range(1, 33))
D = dt.date


@pytest.fixture
def arq(tmp_path):
    return tmp_path / "saude.enc"


def _exames(arq):
    with abrir_saude(arq, CHAVE) as s:
        registrar_exame(s, "p1", "Colesterol total", "190", "mg/dL", D(2026, 1, 10), ("0", "200"), 11, "boss@x.com")
        registrar_exame(s, "p1", "Colesterol total", "215", "mg/dL", D(2026, 7, 10), ("0", "200"), 12, "boss@x.com")
        registrar_exame(s, "p2", "Colesterol total", "150", "mg/dL", D(2026, 7, 10), ("0", "200"), 13, "boss@x.com")


def test_arquivo_de_saude_nao_abre_sem_chave_nem_com_chave_errada(arq):
    _exames(arq)
    with pytest.raises(ChaveInvalida):
        abrir_saude(arq, OUTRA).__enter__()
    with pytest.raises(ValueError):
        abrir_saude(arq, b"curta")


def test_arquivo_em_disco_nao_tem_texto_legivel_e_so_o_dono_le(arq):
    _exames(arq)
    bruto = arq.read_bytes()
    assert b"Colesterol" not in bruto and b"SQLite" not in bruto
    assert stat.S_IMODE(os.stat(arq).st_mode) == 0o600


def test_registrar_e_ler_a_serie_na_ordem_do_tempo(arq):
    _exames(arq)
    with abrir_saude(arq, CHAVE) as s:
        pontos = serie(s, "p1", "Colesterol total", "boss@x.com")
    assert [(p.em, p.valor) for p in pontos] == [(D(2026, 1, 10), "190"), (D(2026, 7, 10), "215")]
    assert pontos[1].fora_da_faixa and not pontos[0].fora_da_faixa


def test_leitura_de_saude_e_registrada(arq):
    _exames(arq)
    with abrir_saude(arq, CHAVE) as s:
        serie(s, "p1", "Colesterol total", "mae@x.com")
        resumo_para_consulta(s, "p1", "boss@x.com")
    with abrir_saude(arq, CHAVE) as s:
        log = [tuple(r) for r in s.con.execute("select quem, pessoa_id, o_que from leitura order by id")]
    assert log == [("mae@x.com", "p1", "serie:Colesterol total"), ("boss@x.com", "p1", "resumo")]


def test_exame_sem_quem_confirmou_a_pessoa_nao_entra(arq):
    with abrir_saude(arq, CHAVE) as s:
        with pytest.raises(ValueError):
            registrar_exame(s, "p1", "Glicose", "90", "mg/dL", D(2026, 1, 1), None, None, "")


def test_resumo_so_da_pessoa_escolhida(arq):
    _exames(arq)
    with abrir_saude(arq, CHAVE) as s:
        txt = resumo_para_consulta(s, "p1", "boss@x.com")
    assert "Colesterol total" in txt and "215" in txt and "150" not in txt and "fora da faixa" in txt


def test_alteracao_so_persiste_ao_sair_sem_erro(arq):
    _exames(arq)
    with pytest.raises(RuntimeError):
        with abrir_saude(arq, CHAVE) as s:
            registrar_exame(s, "p1", "Glicose", "90", "mg/dL", D(2026, 8, 1), None, None, "boss@x.com")
            raise RuntimeError("falhou no meio")
    with abrir_saude(arq, CHAVE) as s:
        assert serie(s, "p1", "Glicose", "boss@x.com") == []


@pytest.mark.parametrize("nivel,grau_,pessoa,alvo,esperado", [
    ("boss", "total", "p0", "p1", True), ("familia_vip", "parcial", "p1", "p1", True), ("familia_vip", "parcial", "p2", "p1", False),
    ("familia_vip", "nenhum", "p1", "p1", False), ("terceiros", "nenhum", None, "p1", False)])
def test_saude_so_para_nivel_permitido_pela_matriz(nivel, grau_, pessoa, alvo, esperado):
    assert pode_ver(Identidade("x@x", pessoa, nivel), grau_, alvo) is esperado


def test_saude_nunca_aparece_no_banco_principal(tmp_path):
    from pathlib import Path
    from gabi.db import conectar, migrar
    con = conectar(tmp_path / "g.db")
    migrar(con, Path(__file__).parent.parent.parent / "migrations")
    nomes = [r[0].lower() for r in con.execute("select name from sqlite_master")] + \
            [r[1].lower() for t in [r[0] for r in con.execute("select name from sqlite_master where type='table'")] for r in con.execute(f"pragma table_info({t})")]
    # única exceção: `exame_doc` (referência do documento e estado; sem valor, marcador nem paciente)
    assert not [n for n in nomes if any(p in n for p in ("exame", "saude", "saúde", "marcador", "laudo")) and n != "exame_doc"]


def test_cofre_antigo_abre_e_ganha_colunas(arq, monkeypatch):
    from gabi.familia import saude
    antigo = """
    create table if not exists exame(
      id integer primary key, pessoa_id text not null, marcador text not null, valor text not null, valor_num real, unidade text,
      em text not null, ref_min text, ref_max text, paperless_id integer, confirmado_por text not null, criado_em text not null);
    create table if not exists proposta_exame(
      id integer primary key, paperless_id integer not null, pessoa_sugerida text, marcador text not null, valor text not null, unidade text,
      em text, ref_min text, ref_max text, estado text not null default 'proposta', criado_em text not null);
    create table if not exists leitura(id integer primary key, quando text not null, quem text not null, pessoa_id text, o_que text not null);
    """
    with monkeypatch.context() as m:
        m.setattr(saude, "ESQUEMA", antigo)
        m.setattr(saude, "_migrar", lambda con: None)
        with abrir_saude(arq, CHAVE) as s:
            registrar_exame(s, "p1", "Glicose", "90", "mg/dL", D(2026, 1, 1), None, 1, "boss@x.com")
            assert "versao" not in {r[1] for r in s.con.execute("pragma table_info(exame)")}
    with abrir_saude(arq, CHAVE) as s:
        r = s.con.execute("select * from exame").fetchone()
        assert (r["marcador"], r["valor"], r["versao"], r["qualitativo"]) == ("Glicose", "90", 1, 0)
        assert {"origem", "versao"} <= {c[1] for c in s.con.execute("pragma table_info(proposta_exame)")}
        assert s.con.execute("select count(*) from marcador_apelido").fetchone()[0] == 0
    with abrir_saude(arq, CHAVE):  # abrir de novo é idempotente
        pass
