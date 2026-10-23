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


# Documento mascarado (legado de 08/10, com "*"): a proposta aponta para ele e aprovar troca o número.

def test_proposta_aponta_para_o_mascarado_do_mesmo_tipo_e_pais(con):
    m = _ativo(con, numero="AA****56", validade=None)
    _ativo(con, numero="ZZ****99", validade=None, pais="PT")
    pid = _propor(con, numero="AB123456", validade="2031-05-01", origem="carga")
    p = con.execute("select * from pessoa_proposta where id=?", (pid,)).fetchone()
    assert p["documento_id"] == m and p["conferir"] == 0


def test_aprovar_sobre_mascarado_troca_o_numero_sem_segundo_documento(con):
    m = _ativo(con, numero="AA****56", validade=None)
    pid = _propor(con, numero="AB123456", validade="2031-05-01", origem="carga")
    r = documentos.decidir(con, pid, "aprovada", "ricardo", AGORA)
    docs = con.execute("select * from pessoa_documento where pessoa_id='ana' and excluido_em is null").fetchall()
    assert r["documento_id"] == m and len(docs) == 1
    assert docs[0]["numero"] == "AB123456" and docs[0]["validade"] == "2031-05-01"


def test_digitos_visiveis_que_nao_batem_dao_conferir(con):
    m = _ativo(con, numero="AA****99", validade=None)
    pid = _propor(con, numero="AB123456", origem="carga")
    p = con.execute("select * from pessoa_proposta where id=?", (pid,)).fetchone()
    assert p["documento_id"] == m and p["conferir"] == 1


def test_cpf_mascarado_com_digitos_que_batem(con):
    m = con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, origem) values ('ana','cpf','***.***.***-25','legado')").lastrowid
    pid = _propor(con, tipo="cpf", numero=CPF_OK, origem="carga")
    p = con.execute("select * from pessoa_proposta where id=?", (pid,)).fetchone()
    assert p["documento_id"] == m and p["conferir"] == 0
    documentos.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert [d["numero"] for d in con.execute("select numero from pessoa_documento where pessoa_id='ana'")] == [CPF_OK]


def test_mascarado_escolhe_o_primeiro_por_id(con):
    m1 = _ativo(con, numero="AA****56", validade=None)
    _ativo(con, numero="BB****56", validade=None)
    pid = _propor(con, numero="AB123456", origem="carga")
    assert con.execute("select documento_id from pessoa_proposta where id=?", (pid,)).fetchone()[0] == m1


def test_mascarado_prefere_o_que_tem_digitos_visiveis_batendo(con):
    m1 = con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, origem) values ('ana','outro','****11','legado')").lastrowid
    m2 = con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, origem) values ('ana','outro','****22','legado')").lastrowid
    a = _propor(con, tipo="outro", numero="998822", origem="carga")
    b = _propor(con, tipo="outro", numero="557711", origem="carga")
    c = _propor(con, tipo="outro", numero="440033", origem="carga")
    linhas = {r["id"]: r for r in con.execute("select id, documento_id, conferir from pessoa_proposta")}
    assert (linhas[a]["documento_id"], linhas[a]["conferir"]) == (m2, 0)
    assert (linhas[b]["documento_id"], linhas[b]["conferir"]) == (m1, 0)
    assert (linhas[c]["documento_id"], linhas[c]["conferir"]) == (m1, 1)  # nenhum bate: primeiro por id, conferir


def test_duas_propostas_no_mesmo_mascarado_nao_sobrescrevem_uma_a_outra(con):
    m = _ativo(con, numero="AA****56", validade=None)
    p1 = _propor(con, numero="AB123456", validade="2031-05-01", origem="carga")
    p2 = _propor(con, numero="CD999956", validade="2029-01-01", origem="carga")
    assert {r[0] for r in con.execute("select documento_id from pessoa_proposta")} == {m}
    documentos.decidir(con, p1, "aprovada", "ricardo", AGORA)
    r2 = documentos.decidir(con, p2, "aprovada", "ricardo", AGORA)
    docs = {d["numero"]: dict(d) for d in con.execute("select * from pessoa_documento where pessoa_id='ana' and excluido_em is null")}
    assert docs["AB123456"]["validade"] == "2031-05-01" and docs["AB123456"]["id"] == m
    assert docs["CD999956"]["validade"] == "2029-01-01" and r2["documento_id"] != m


def test_aprovar_sobre_mascarado_troca_a_origem(con):
    _ativo(con, numero="AA****56", validade=None)
    pid = _propor(con, numero="AB123456", origem="carga")
    documentos.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert con.execute("select origem from pessoa_documento where pessoa_id='ana'").fetchone()[0] == "carga"


def test_carga_nao_repropoe_numero_recusado_e_hermes_sim(con):
    pid = _propor(con, numero="AB123456", origem="carga")
    documentos.decidir(con, pid, "recusada", "ricardo", AGORA)
    assert _propor(con, numero="ab 123456", origem="carga") is None
    assert _propor(con, numero="AB123456", origem="hermes") is not None
