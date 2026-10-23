"""Migração 0077 (cadastro familiar): cópia dos documentos legados e checks das tabelas novas.
Consome: gabi.db.migrar, migrations/0077_familia.sql."""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from gabi.db import migrar

MIGRACOES = Path(__file__).resolve().parent.parent.parent / "migrations"


def _banco(tmp_path, pessoas, todas=False):
    """Aplica as migrações até a 0076, grava as pessoas e só então aplica a 0077 (banco de produção antes da virada)."""
    pasta = tmp_path / "antes"
    pasta.mkdir()
    for arq in MIGRACOES.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if arq.name < "0077":
            shutil.copy(arq, pasta / arq.name)
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    migrar(con, pasta)
    for pid, nome, dados, excluido in pessoas:
        con.execute("insert into pessoa(id, nome, dados, excluido_em) values (?,?,?,?)",
                    (pid, nome, dados if isinstance(dados, str) or dados is None else json.dumps(dados), excluido))
    nova = tmp_path / "depois"
    nova.mkdir()
    for arq in MIGRACOES.glob("[0-9][0-9][0-9][0-9]_*.sql") if todas else [next(MIGRACOES.glob("0077_*.sql"))]:
        shutil.copy(arq, nova / arq.name)
    for arq in pasta.iterdir():
        shutil.copy(arq, nova / arq.name)
    migrar(con, nova)
    return con


DOCS = [{"tipo": "CPF", "numero": "123"}, {"tipo": "Passaporte", "numero": "AB1", "emissor": "PF"},
        {"tipo": "Título", "numero": "9"}]


def test_copia_documentos_legados(tmp_path):
    dados = {"documentos": DOCS, "apelido": "x"}
    con = _banco(tmp_path, [("p1", "Ana", dados, None)])
    linhas = con.execute("select * from pessoa_documento where pessoa_id='p1' order by id").fetchall()
    assert [l["tipo"] for l in linhas] == ["cpf", "passaporte", "outro"]
    assert {l["origem"] for l in linhas} == {"legado"}
    assert {l["pais"] for l in linhas} == {"BR"}
    assert [l["emissor"] for l in linhas] == [None, "PF", None]
    assert json.loads(con.execute("select dados from pessoa where id='p1'").fetchone()[0]) == dados


def test_normaliza_variantes_de_tipo(tmp_path):
    docs = [{"tipo": t, "numero": "1"} for t in
            ["RG", "Identidade", "Carteira de Motorista", "CNH", "Habilitação", " cpf "]]
    con = _banco(tmp_path, [("p1", "Ana", {"documentos": docs}, None)])
    tipos = [r[0] for r in con.execute("select tipo from pessoa_documento order by id")]
    assert tipos == ["rg", "rg", "cnh", "cnh", "cnh", "cpf"]


def test_pessoa_excluida_nao_copia(tmp_path):
    con = _banco(tmp_path, [("p1", "Ana", {"documentos": DOCS}, "2026-10-01T00:00:00Z")])
    assert con.execute("select count(*) from pessoa_documento").fetchone()[0] == 0


def test_dados_estranhos_nao_quebram(tmp_path):
    con = _banco(tmp_path, [("a", "A", None, None), ("b", "B", "nao é json", None),
                            ("c", "C", {"documentos": "x"}, None), ("d", "D", {"documentos": [1, {"tipo": "cpf"}, {"tipo": "cpf", "numero": ""}]}, None)])
    assert con.execute("select count(*) from pessoa_documento").fetchone()[0] == 0


def test_checks(tmp_path):
    con = _banco(tmp_path, [("p1", "Ana", {}, None)])
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into pessoa_documento(pessoa_id,tipo,numero,origem) values ('p1','titulo','1','ricardo')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into pessoa_documento(pessoa_id,tipo,numero,origem) values ('p1','cpf','1','outra')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into pessoa_proposta(pessoa_id,tipo,numero,origem) values ('p1','cpf','1','email')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into pessoa_proposta(pessoa_id,tipo,numero,origem,estado) values ('p1','cpf','1','hermes','x')")


def test_indice_unico_das_propostas_abertas(tmp_path):
    con = _banco(tmp_path, [("p1", "Ana", {}, None)])
    ins = "insert into pessoa_proposta(pessoa_id,tipo,numero,origem,estado) values ('p1','cpf','1','hermes',?)"
    con.execute(ins, ("pendente",))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("pendente",))
    con.execute(ins, ("recusada",))
    con.execute(ins, ("recusada",))



def test_numero_null_ou_none_nao_vira_documento(tmp_path):
    con = _banco(tmp_path, [("p1", "Ana", {"documentos": [{"tipo": "rg", "numero": "null"}, {"tipo": "passaporte", "numero": "None"},
                                                          {"tipo": "cpf", "numero": "123"}]}, None)], todas=True)
    # 0077 já rodou em produção copiando o texto "null"; a 0079 tira esses do cadastro (excluido_em, dá para desfazer)
    assert [r[0] for r in con.execute("select tipo from pessoa_documento where excluido_em is null")] == ["cpf"]
