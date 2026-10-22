"""Fichas da família: listar, ficha, resolver, vencimentos, divergências e auditoria.
Consome: gabi.familia.fichas, migrações."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.familia import fichas
from gabi.familia.fichas import ErroFamilia

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 22)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _pessoa(con, pid, nome, **dados):
    con.execute("insert into pessoa(id, nome, dados) values (?,?,?)", (pid, nome, json.dumps(dados)))


def _doc(con, pid, tipo, numero, pais="BR", validade=None, emissao=None, emissor=None, origem="ricardo"):
    return con.execute("insert into pessoa_documento(pessoa_id, tipo, pais, numero, emissor, emissao, validade, origem)"
                       " values (?,?,?,?,?,?,?,?)", (pid, tipo, pais, numero, emissor, emissao, validade, origem)).lastrowid


def test_listar_nao_traz_numero(con):
    _pessoa(con, "ana", "Ana", apelido="Aninha", nascimento="2000-01-02")
    _doc(con, "ana", "cpf", "11122233344")
    _doc(con, "ana", "rg", "999")
    gone = _doc(con, "ana", "cnh", "555")
    con.execute("update pessoa_documento set excluido_em='2026-01-01' where id=?", (gone,))
    r = fichas.listar(con)
    assert r == [{"id": "ana", "nome": "Ana", "apelido": "Aninha", "parentesco": None, "nascimento": "2000-01-02", "documentos_qtd": 2}]
    assert "11122233344" not in json.dumps(r)


def test_ficha_dois_passaportes_e_contatos(con):
    _pessoa(con, "ana", "Ana", nome_completo="Ana Souza", telefone="+5511999", telefones=["+5511999", "+5511888"],
            email="a@x.com", enderecos=["Rua 1"])
    _doc(con, "ana", "passaporte", "BR1", pais="BR", origem="legado")
    _doc(con, "ana", "passaporte", "PT1", pais="PT", origem="carga")
    f = fichas.ficha(con, "ana")
    assert [(d["pais"], d["origem"], d["numero"]) for d in f["documentos"]] == [("BR", "legado", "BR1"), ("PT", "carga", "PT1")]
    assert f["telefones"] == ["+5511999", "+5511888"] and f["emails"] == ["a@x.com"] and f["enderecos"] == ["Rua 1"]
    assert f["nome_completo"] == "Ana Souza" and f["divergencias"] == []
    with pytest.raises(ErroFamilia) as e:
        fichas.ficha(con, "zzz")
    assert e.value.codigo == "nao_encontrado"


def test_divergencia_por_validade(con):
    _pessoa(con, "ana", "Ana")
    d = _doc(con, "ana", "passaporte", "BR1", validade="2027-01-01")
    con.execute("insert into pessoa_proposta(pessoa_id, documento_id, tipo, numero, validade, origem) values ('ana',?,'passaporte','BR1','2031-01-01','hermes')", (d,))
    con.execute("insert into pessoa_proposta(pessoa_id, documento_id, tipo, numero, validade, origem, estado) values ('ana',?,'passaporte','BR1','2035-01-01','hermes','recusada')", (d,))
    assert fichas.ficha(con, "ana")["divergencias"] == [{"documento_id": d, "tipo": "passaporte", "campos": ["validade"]}]


def test_resolver_pessoa(con):
    _pessoa(con, "ana", "Ana")
    _pessoa(con, "anap", "Ana Paula", apelido="Paulinha")
    _pessoa(con, "bia", "Beatriz", nome_completo="Beatriz Lima", apelido="Bia")
    assert fichas.resolver_pessoa(con, "ana") == "ana"
    assert fichas.resolver_pessoa(con, " Paulinha ") == "anap"
    assert fichas.resolver_pessoa(con, "BEATRIZ LIMA") == "bia"
    with pytest.raises(ErroFamilia) as e:
        fichas.resolver_pessoa(con, "ana p")
    assert e.value.codigo == "pessoa_ambigua" and e.value.candidatos == ["Ana Paula"]
    with pytest.raises(ErroFamilia) as e:
        fichas.resolver_pessoa(con, "carlos")
    assert e.value.codigo == "pessoa_ambigua" and e.value.candidatos == []


def test_vencimentos(con):
    _pessoa(con, "ana", "Ana")
    for n, v in [("a", "2027-03-22"), ("b", "2026-10-12"), ("c", "2026-09-12"), ("d", "2027-05-22"), ("e", None)]:
        _doc(con, "ana", "outro", n, validade=v)
    r = fichas.vencimentos(con, HOJE, 6)
    assert [(x["validade"], x["vencido"]) for x in r] == [("2026-10-12", True), ("2027-03-22", False)]
    assert all("numero" not in x for x in r) and r[0]["nome"] == "Ana" and r[0]["pessoa_id"] == "ana"


def test_auditar_leitura_sem_numero(con):
    _pessoa(con, "ana", "Ana")
    fichas.auditar_leitura(con, "ana", ["cpf", "passaporte"], "hermes", dt.datetime(2026, 10, 22, 9, tzinfo=dt.timezone.utc))
    r = con.execute("select quando, quem, o_que, origem from decisao").fetchone()
    assert r["o_que"] == "Hermes consultou a ficha de ana (documentos: cpf, passaporte)" and r["origem"] == "familia"
    assert r["quando"] == "2026-10-22T09:00:00Z"
