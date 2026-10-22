"""Propostas de documento: validação, atualização do ativo, aprovação, recusa e conflitos.
Consome: gabi.familia.documentos, gabi.familia.fichas, migrações."""
import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.familia import documentos, fichas
from gabi.familia.fichas import ErroFamilia

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)
CPF_OK = "529.982.247-25"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana','{}')")
    return c


def _propor(con, **kw):
    base = dict(tipo="passaporte", numero="AB123456", origem="hermes", agora=AGORA)
    base.update(kw)
    return documentos.propor(con, "ana", **base)


def _ativo(con, numero="AB123456", validade="2030-01-01", **extra):
    cols = {"pessoa_id": "ana", "tipo": "passaporte", "numero": numero, "validade": validade, "origem": "legado", **extra}
    return con.execute(f"insert into pessoa_documento({','.join(cols)}) values ({','.join('?' * len(cols))})",
                       tuple(cols.values())).lastrowid


def _erro(fn, *a, **k):
    with pytest.raises(ErroFamilia) as e:
        fn(*a, **k)
    return e.value.codigo


def test_cpf_dv_invalido_confere(con):
    pid = _propor(con, tipo="cpf", numero="111.444.777-00")
    assert con.execute("select conferir from pessoa_proposta where id=?", (pid,)).fetchone()[0] == 1


def test_cpf_valido_nao_confere(con):
    pid = _propor(con, tipo="cpf", numero=CPF_OK)
    assert con.execute("select conferir from pessoa_proposta where id=?", (pid,)).fetchone()[0] == 0


def test_validacoes(con):
    assert _erro(_propor, con, validade="01/02/2030") == "valor_invalido"
    assert _erro(_propor, con, emissao="2030-13-40") == "valor_invalido"
    assert _erro(_propor, con, numero="") == "valor_invalido"
    assert _erro(_propor, con, numero="x" * 41) == "valor_invalido"
    assert _erro(_propor, con, tipo="titulo") == "campo_invalido"
    assert _erro(_propor, con, origem="ricardo") == "requisicao_invalida"
    assert _erro(_propor, con, pais="BRA") == "valor_invalido"
    assert _erro(documentos.propor, con, "zzz", tipo="rg", numero="1", origem="hermes", agora=AGORA) == "nao_encontrado"


def test_identica_ao_ativo_devolve_none(con):
    _ativo(con, validade="2030-01-01", emissor="PF")
    assert _propor(con, numero="ab-123.456", validade="2030-01-01") is None
    assert _propor(con, validade="2030-01-01", emissor="PF") is None
    assert con.execute("select count(*) from pessoa_proposta").fetchone()[0] == 0


def test_mesmo_numero_validade_nova_atualiza_o_ativo(con):
    did = _ativo(con, validade="2030-01-01", emissor="PF")
    pid = _propor(con, validade="2035-01-01")
    p = documentos.listar_propostas(con)[0]
    assert p["id"] == pid and p["documento_id"] == did
    assert p["atual"]["validade"] == "2030-01-01" and p["proposto"]["validade"] == "2035-01-01"
    documentos.decidir(con, pid, "aprovada", "boss", AGORA)
    linhas = con.execute("select validade, emissor, origem from pessoa_documento").fetchall()
    assert len(linhas) == 1 and tuple(linhas[0]) == ("2035-01-01", "PF", "legado")


def test_campos_vazios_nao_sobrescrevem_nem_divergem(con):
    did = _ativo(con, validade="2030-01-01", emissor="PF", emissao="2020-01-01", paperless_id=7)
    pid = _propor(con, numero="AB 123456", validade="2035-01-01", emissor="", emissao=None, paperless_id=0)
    assert fichas.ficha(con, "ana")["divergencias"] == [{"documento_id": did, "tipo": "passaporte", "campos": ["validade"]}]
    documentos.decidir(con, pid, "aprovada", "boss", AGORA)
    r = con.execute("select numero, validade, emissor, emissao, paperless_id from pessoa_documento").fetchone()
    assert tuple(r) == ("AB123456", "2035-01-01", "PF", "2020-01-01", 7)


def test_aprovar_novo_origem(con):
    a = _propor(con, numero="AB111111", origem="hermes")
    b = _propor(con, numero="AB222222", origem="carga")
    documentos.decidir(con, a, "aprovada", "boss", AGORA)
    documentos.decidir(con, b, "aprovada", "boss", AGORA)
    r = {x["numero"]: x["origem"] for x in con.execute("select numero, origem from pessoa_documento")}
    assert r == {"AB111111": "ricardo", "AB222222": "carga"}


def test_recusar_nao_muda_nada(con):
    did = _ativo(con)
    pid = _propor(con, validade="2035-01-01")
    antes = [tuple(r) for r in con.execute("select * from pessoa_documento")]
    documentos.decidir(con, pid, "recusada", "boss", AGORA)
    assert [tuple(r) for r in con.execute("select * from pessoa_documento")] == antes
    assert con.execute("select estado from pessoa_proposta").fetchone()[0] == "recusada" and did
    assert documentos.listar_propostas(con) == [] and len(documentos.listar_propostas(con, "recusada")) == 1


def test_decidir_duas_vezes_conflito(con):
    pid = _propor(con)
    documentos.decidir(con, pid, "aprovada", "boss", AGORA)
    assert _erro(documentos.decidir, con, pid, "recusada", "boss", AGORA) == "conflito"
    assert _erro(documentos.decidir, con, 999, "aprovada", "boss", AGORA) == "nao_encontrado"
    assert _erro(documentos.decidir, con, pid, "talvez", "boss", AGORA) == "requisicao_invalida"
    assert con.execute("select count(*) from pessoa_documento").fetchone()[0] == 1


def test_proposta_aberta_repetida_devolve_a_anterior(con):
    a = _propor(con)
    assert _propor(con, numero="ab-123456", validade="2031-01-01") == a
    assert con.execute("select count(*) from pessoa_proposta").fetchone()[0] == 1


def test_auditoria_sem_numero(con):
    pid = _propor(con, numero="AB987654")
    documentos.decidir(con, pid, "aprovada", "boss", AGORA)
    o = con.execute("select o_que, origem from decisao where origem='familia'").fetchone()
    assert "AB987654" not in o["o_que"] and str(pid) in o["o_que"] and "ana" in o["o_que"]
    assert "passaporte" in o["o_que"] and "aprovada" in o["o_que"]
