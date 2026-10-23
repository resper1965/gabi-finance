"""Migrações da família: 0077 (cópia dos documentos legados e checks) e 0081 (família em documento/documento_proposta).
Consome: gabi.db.migrar, migrations/0077_familia.sql, migrations/0081_documentos.sql, gabi.familia."""
import datetime as dt
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
    # `todas` para antes da 0081 (que renomeia as tabelas da família para *_legado; testada abaixo).
    for arq in [a for a in MIGRACOES.glob("[0-9][0-9][0-9][0-9]_*.sql") if a.name < "0081"] if todas else [next(MIGRACOES.glob("0077_*.sql"))]:
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


# ---------------- 0081: a família passa para documento/documento_proposta ----------------

AGORA = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)
_INS_DOC = ("insert into pessoa_documento(pessoa_id, tipo, pais, numero, emissor, emissao, validade, paperless_id, origem, criado_em,"
            " atualizado_em) values (?,?,?,?,?,?,?,?,?,'2026-10-01T00:00:00Z','2026-10-02T00:00:00Z')")


def _ate_0080(tmp_path):
    """Banco de produção antes da 0081: todas as migrações anteriores, sem o atalho do conftest."""
    pasta = tmp_path / "ate0080"
    pasta.mkdir()
    for arq in MIGRACOES.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if arq.name < "0081":
            shutil.copy(arq, pasta / arq.name)
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    migrar(con, pasta)
    con.execute("insert into pessoa(id, nome, dados) values ('ana','Ana','{\"apelido\":\"Aninha\"}')")
    return con


def _aplicar_0081(con, tmp_path):
    pasta = tmp_path / "todas"
    pasta.mkdir()
    for arq in MIGRACOES.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        shutil.copy(arq, pasta / arq.name)
    migrar(con, pasta)


def _familia_antes(con):
    """3 documentos (um sem datas, um com emissão e validade, um vencido) e 1 proposta pendente que o substitui."""
    con.execute(_INS_DOC, ("ana", "cpf", "BR", "529.982.247-25", None, None, None, None, "legado"))
    p = con.execute(_INS_DOC, ("ana", "passaporte", "BR", "FK077009", "PF", "2021-11-03", "2026-11-02", 12, "carga")).lastrowid
    con.execute(_INS_DOC, ("ana", "passaporte", "PT", "CB123456", "SEF", None, "2026-10-01", None, "ricardo"))
    con.execute("insert into pessoa_proposta(pessoa_id, documento_id, tipo, pais, numero, emissor, emissao, validade, paperless_id,"
                " origem, conferir, criada_em) values ('ana',?,'passaporte','BR','FK077009',null,'2026-10-20','2036-10-19',15,'carga',1,"
                "'2026-10-21T10:00:00Z')", (p,))
    con.execute("insert into pessoa_proposta(pessoa_id, tipo, pais, numero, origem, estado, criada_em, decidida_em, decidida_por)"
                " values ('ana','rg','BR','12345','carga','recusada','2026-10-20T10:00:00Z','2026-10-20T11:00:00Z','ricardo')")


def test_0081_copia_a_familia(tmp_path):
    con = _ate_0080(tmp_path)
    _familia_antes(con)
    _aplicar_0081(con, tmp_path)
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"pessoa_documento_legado", "pessoa_proposta_legado", "bem", "documento", "documento_numero", "documento_data",
            "documento_proposta", "documento_leitura"} <= nomes
    assert not {"pessoa_documento", "pessoa_proposta"} & nomes
    docs = [dict(r) for r in con.execute("select id, titular_tipo, titular_id, tipo, pais, emissor, paperless_id, origem from documento order by id")]
    assert docs == [
        {"id": 1, "titular_tipo": "pessoa", "titular_id": "ana", "tipo": "cpf", "pais": "BR", "emissor": None, "paperless_id": None, "origem": "legado"},
        {"id": 2, "titular_tipo": "pessoa", "titular_id": "ana", "tipo": "passaporte", "pais": "BR", "emissor": "PF", "paperless_id": 12, "origem": "carga"},
        {"id": 3, "titular_tipo": "pessoa", "titular_id": "ana", "tipo": "passaporte", "pais": "PT", "emissor": "SEF", "paperless_id": None, "origem": "ricardo"}]
    assert [tuple(r) for r in con.execute("select documento_id, nome, valor from documento_numero order by documento_id")] == [
        (1, "numero", "529.982.247-25"), (2, "numero", "FK077009"), (3, "numero", "CB123456")]
    assert [tuple(r) for r in con.execute("select documento_id, tipo, data from documento_data order by documento_id, tipo")] == [
        (2, "emissao", "2021-11-03"), (2, "validade", "2026-11-02"), (3, "validade", "2026-10-01")]
    p = con.execute("select * from documento_proposta where estado='pendente'").fetchone()
    assert (p["id"], p["documento_id"], p["paperless_id"], p["conferir"], p["origem"]) == (1, 2, 15, 1, "carga")
    assert json.loads(p["doc"]) == {"titular_tipo": "pessoa", "titular_id": "ana", "tipo": "passaporte", "pais": "BR", "emissor": None,
                                    "numeros": [{"nome": "numero", "valor": "FK077009"}],
                                    "datas": [{"tipo": "emissao", "data": "2026-10-20"}, {"tipo": "validade", "data": "2036-10-19"}]}
    # As decididas vêm junto: a carga não repropõe o que o Ricardo recusou.
    assert [tuple(r) for r in con.execute("select id, estado, decidida_por from documento_proposta order by id")] == [
        (1, "pendente", None), (2, "recusada", "ricardo")]


def test_familia_responde_igual(tmp_path):
    """Review Focus 5: o esperado é a resposta do código antigo sobre as tabelas antigas, gravada aqui como literal."""
    from gabi.familia import documentos, fichas
    con = _ate_0080(tmp_path)
    _familia_antes(con)
    _aplicar_0081(con, tmp_path)
    base = {"id": None, "tipo": "passaporte", "pais": "BR", "numero": None, "emissor": None, "emissao": None, "validade": None,
            "paperless_id": None, "origem": None, "atualizado_em": "2026-10-02T00:00:00Z"}
    assert fichas.ficha(con, "ana") == {
        "id": "ana", "nome": "Ana", "nome_completo": None, "apelido": "Aninha", "parentesco": None, "nascimento": None,
        "telefones": [], "emails": [], "enderecos": [],
        "documentos": [{**base, "id": 1, "tipo": "cpf", "numero": "529.982.247-25", "origem": "legado"},
                       {**base, "id": 2, "numero": "FK077009", "emissor": "PF", "emissao": "2021-11-03", "validade": "2026-11-02",
                        "paperless_id": 12, "origem": "carga"},
                       {**base, "id": 3, "pais": "PT", "numero": "CB123456", "emissor": "SEF", "validade": "2026-10-01", "origem": "ricardo"}],
        "divergencias": [{"documento_id": 2, "tipo": "passaporte", "campos": ["emissao", "validade"]}]}
    assert fichas.vencimentos(con, dt.date(2026, 10, 22), 6) == [
        {"pessoa_id": "ana", "nome": "Ana", "tipo": "passaporte", "pais": "PT", "validade": "2026-10-01", "vencido": True},
        {"pessoa_id": "ana", "nome": "Ana", "tipo": "passaporte", "pais": "BR", "validade": "2026-11-02", "vencido": False}]
    assert documentos.listar_propostas(con) == [{
        "id": 1, "pessoa_id": "ana", "nome": "Ana", "documento_id": 2, "origem": "carga", "conferir": True, "estado": "pendente",
        "criada_em": "2026-10-21T10:00:00Z", "decidida_em": None, "decidida_por": None,
        "atual": {"id": 2, "tipo": "passaporte", "pais": "BR", "numero": "FK077009", "emissor": "PF", "emissao": "2021-11-03",
                  "validade": "2026-11-02", "paperless_id": 12},
        "proposto": {"tipo": "passaporte", "pais": "BR", "numero": "FK077009", "emissor": None, "emissao": "2026-10-20",
                     "validade": "2036-10-19", "paperless_id": 15}}]
    assert fichas.listar(con) == [{"id": "ana", "nome": "Ana", "apelido": "Aninha", "parentesco": None, "nascimento": None,
                                   "documentos_qtd": 3}]
    # A carga continua sem repropor o RG recusado antes da migração.
    assert documentos.propor(con, "ana", tipo="rg", numero="12.345", origem="carga", agora=AGORA) is None
