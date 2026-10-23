"""Repositório de documentos: propor, decidir (com correção e bem novo), listar, consultar, vencimentos e titular.
Consome: gabi.documentos.repositorio, migrações."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.documentos import repositorio as rep
from gabi.documentos.repositorio import ErroDocumentos

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)
HOJE = dt.date(2026, 10, 22)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana','{}')")
    c.execute("insert into pessoa(id, nome, dados) values ('bia','Beatriz','{}')")
    c.execute("insert into bem(id, tipo, nome, dados) values ('carro','veiculo','Carro','{\"modelo\":\"Onix\"}')")
    c.execute("insert into bem(id, tipo, nome, dados) values ('apto','imovel','Apartamento','{\"endereco\":\"Rua das Flores, 10\"}')")
    return c


def _doc(titular_tipo="pessoa", titular_id="ana", tipo="passaporte", numero="FK077009", datas=None, **extra):
    d = {"titular_tipo": titular_tipo, "titular_id": titular_id, "tipo": tipo, "pais": "BR", "emissor": None,
         "numeros": [{"nome": "numero", "valor": numero}],
         "datas": [{"tipo": t, "data": v} for t, v in (datas or {"validade": "2030-01-01"}).items()]}
    d.update(extra)
    return d


def _propor(con, doc=None, **kw):
    base = dict(origem="leitura", paperless_id=None, conferir=False, motivos=[], agora=AGORA)
    base.update(kw)
    return rep.propor(con, doc or _doc(), **base)


def _aprovado(con, doc=None, **kw):
    r = rep.decidir(con, _propor(con, doc, **kw), "aprovada", "ricardo", AGORA)
    return r["documento_id"]


def _erro(fn, *a, **k):
    with pytest.raises(ErroDocumentos) as e:
        fn(*a, **k)
    return e.value.codigo


def test_decidir_aprovada_cria_documento_e_decisao_sem_numero(con):
    pid = _propor(con, paperless_id=31)
    r = rep.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert r == {"proposta_id": pid, "estado": "aprovada", "documento_id": r["documento_id"], "bem_id": None} and r["documento_id"]
    d = rep.consultar(con, titular_id="ana")
    assert len(d) == 1 and d[0]["numeros"] == [{"nome": "numero", "valor": "FK077009"}] and d[0]["paperless_id"] == 31
    assert d[0]["datas"] == [{"tipo": "validade", "data": "2030-01-01"}] and d[0]["origem"] == "leitura" and d[0]["titular_nome"] == "Ana"
    o = con.execute("select o_que, origem, quem from decisao").fetchone()
    assert o["origem"] == "documentos" and o["quem"] == "ricardo"
    assert "FK077009" not in o["o_que"] and str(pid) in o["o_que"] and "passaporte" in o["o_que"] and "aprovada" in o["o_que"]


def test_propor_igual_ao_ativo_e_none(con):
    _aprovado(con)
    assert _propor(con) is None
    assert _propor(con, _doc(numero="FK 077.009")) is None  # mesmo número, só formatação
    assert con.execute("select count(*) from documento_proposta where estado='pendente'").fetchone()[0] == 0


def test_pendente_igual_devolve_o_mesmo_id(con):
    a = _propor(con)
    assert _propor(con, _doc(datas={"validade": "2031-01-01"})) == a
    assert con.execute("select count(*) from documento_proposta").fetchone()[0] == 1


def test_data_nova_e_proposta_que_substitui(con):
    did = _aprovado(con)
    pid = _propor(con, _doc(datas={"validade": "2035-01-01"}))
    p = rep.listar_propostas(con)[0]
    assert p["id"] == pid and p["atual"]["id"] == did and p["atual"]["datas"] == [{"tipo": "validade", "data": "2030-01-01"}]
    assert p["doc"]["datas"] == [{"tipo": "validade", "data": "2035-01-01"}] and p["titular"] == {"tipo": "pessoa", "id": "ana", "nome": "Ana"}
    r = rep.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert r["documento_id"] == did
    assert rep.consultar(con, titular_id="ana")[0]["datas"] == [{"tipo": "validade", "data": "2035-01-01"}]
    assert con.execute("select count(*) from documento").fetchone()[0] == 1


def test_numero_e_guardado_como_esta(con):
    did = _aprovado(con, _doc(tipo="cpf", numero="529.982.247-25", datas={}))
    assert con.execute("select valor from documento_numero where documento_id=?", (did,)).fetchone()[0] == "529.982.247-25"


def test_correcao_troca_titular_e_numero(con):
    pid = _propor(con, _doc(numero="FKO77009"), conferir=True, motivos=["validade_antes_da_emissao"])
    p = rep.listar_propostas(con)[0]
    assert p["conferir"] is True and p["motivos"] == ["validade_antes_da_emissao"]
    r = rep.decidir(con, pid, "aprovada", "ricardo", AGORA,
                    correcao={"titular_id": "bia", "numeros": [{"nome": "numero", "valor": "FK077009"}]})
    assert [d["titular_id"] for d in rep.consultar(con)] == ["bia"]
    assert rep.consultar(con, titular_id="bia")[0]["numeros"][0]["valor"] == "FK077009" and r["bem_id"] is None
    assert "FK077009" not in con.execute("select o_que from decisao").fetchone()[0]


def test_correcao_invalida(con):
    pid = _propor(con)
    assert _erro(rep.decidir, con, pid, "aprovada", "ricardo", AGORA, correcao={"titular_id": "zzz"}) == "titular_invalido"
    assert _erro(rep.decidir, con, pid, "aprovada", "ricardo", AGORA, correcao={"datas": [{"tipo": "validade", "data": "30/01/2030"}]}) == "valor_invalido"
    assert _erro(rep.decidir, con, pid, "aprovada", "ricardo", AGORA, correcao={"senha": "x"}) == "requisicao_invalida"
    assert rep.listar_propostas(con)[0]["estado"] == "pendente"


def test_bem_novo_vira_bem(con):
    doc = _doc("bem", None, "crlv", "ABC1D23", {"vencimento": "2027-03-31"})
    doc["numeros"] = [{"nome": "placa", "valor": "ABC1D23"}, {"nome": "renavam", "valor": "01234567890"}]
    pid = _propor(con, doc, bem_novo={"tipo": "veiculo", "nome": "Moto Honda", "dados": {"modelo": "CG 160"}}, conferir=True,
                  motivos=["titular_desconhecido"])
    p = rep.listar_propostas(con)[0]
    assert p["titular"] is None and p["bem_novo"]["nome"] == "Moto Honda"
    r = rep.decidir(con, pid, "aprovada", "ricardo", AGORA)
    b = {x["id"]: x for x in rep.bens(con)}[r["bem_id"]]
    assert b["tipo"] == "veiculo" and b["nome"] == "Moto Honda" and b["dados"] == {"modelo": "CG 160"}
    assert rep.consultar(con, titular_tipo="bem", titular_id=r["bem_id"])[0]["tipo"] == "crlv"
    assert rep.resolver_titular(con, {"placa": "abc-1d23"}) == ("bem", r["bem_id"])


def test_bem_novo_ignorado_quando_a_correcao_escolhe_titular(con):
    pid = _propor(con, _doc("bem", None, "apolice", "123"), bem_novo={"tipo": "outro", "nome": "Coisa"})
    r = rep.decidir(con, pid, "aprovada", "ricardo", AGORA, correcao={"titular_id": "carro"})
    assert r["bem_id"] is None and [b["id"] for b in rep.bens(con)] == ["apto", "carro"]
    assert rep.consultar(con, titular_id="carro")[0]["tipo"] == "apolice"


def test_recusar_nao_muda_nada(con):
    pid = _propor(con, bem_novo=None)
    r = rep.decidir(con, pid, "recusada", "ricardo", AGORA)
    assert r == {"proposta_id": pid, "estado": "recusada", "documento_id": None, "bem_id": None}
    assert rep.consultar(con) == [] and rep.listar_propostas(con) == []
    assert [p["id"] for p in rep.listar_propostas(con, "recusada")] == [pid]


def test_decidir_duas_vezes_conflito(con):
    pid = _propor(con)
    rep.decidir(con, pid, "aprovada", "ricardo", AGORA)
    assert _erro(rep.decidir, con, pid, "recusada", "ricardo", AGORA) == "conflito"
    assert _erro(rep.decidir, con, 999, "aprovada", "ricardo", AGORA) == "nao_encontrado"
    assert _erro(rep.decidir, con, pid, "talvez", "ricardo", AGORA) == "requisicao_invalida"


def test_propor_valida(con):
    assert _erro(_propor, con, _doc(titular_tipo="pet")) == "valor_invalido"
    assert _erro(_propor, con, _doc(datas={"prazo": "2030-01-01"})) == "valor_invalido"
    assert _erro(_propor, con, _doc(datas={"validade": "2030-02-30"})) == "valor_invalido"
    assert _erro(_propor, con, _doc(titular_id="zzz")) == "titular_invalido"
    assert _erro(_propor, con, _doc("bem", None)) == "titular_invalido"  # sem titular e sem bem novo
    assert _erro(_propor, con, origem="email") == "requisicao_invalida"
    assert _erro(_propor, con, _doc(pais="BRA")) == "valor_invalido"


def test_vencimentos_usa_a_maior_data_e_respeita_a_janela(con):
    a = _aprovado(con, _doc("bem", "carro", "apolice", "A1", {"vigencia_inicio": "2025-11-01", "vigencia_fim": "2026-11-01",
                                                              "vencimento": "2026-12-15"}))
    _aprovado(con, _doc(tipo="cnh", numero="C1", datas={"emissao": "2016-01-01", "validade": "2026-10-10"}))
    _aprovado(con, _doc(tipo="rg", numero="R1", datas={"validade": "2026-09-01"}))  # vencido há mais de 30 dias: fora
    _aprovado(con, _doc(tipo="passaporte", numero="P1", datas={"validade": "2028-01-01"}))  # além da janela: fora
    r = rep.vencimentos(con, HOJE, 3)
    assert [(v["tipo"], v["data_tipo"], v["data"], v["vencido"]) for v in r] == [
        ("cnh", "validade", "2026-10-10", True), ("apolice", "vencimento", "2026-12-15", False)]
    assert r[1] == {"documento_id": a, "titular_tipo": "bem", "titular_id": "carro", "titular_nome": "Carro", "tipo": "apolice",
                    "data_tipo": "vencimento", "data": "2026-12-15", "vencido": False}
    assert "A1" not in json.dumps(r)


def test_consultar_filtra(con):
    _aprovado(con, _doc("bem", "carro", "crlv", "ABC1D23", {}))
    _aprovado(con, _doc(tipo="cnh", numero="C1", emissor="DETRAN-SP"))
    assert [d["tipo"] for d in rep.consultar(con, titular_tipo="bem")] == ["crlv"]
    assert [d["tipo"] for d in rep.consultar(con, tipo="cnh")] == ["cnh"]
    assert [d["tipo"] for d in rep.consultar(con, texto="detran")] == ["cnh"]
    assert [d["tipo"] for d in rep.consultar(con, texto="carro")] == ["crlv"]  # pelo nome do titular
    con.execute("update documento set excluido_em='2026-10-22T00:00:00Z' where tipo='cnh'")
    assert [d["tipo"] for d in rep.consultar(con)] == ["crlv"]


def test_resolver_titular(con):
    _aprovado(con, _doc(tipo="cpf", numero="529.982.247-25", datas={}))
    _aprovado(con, _doc("bem", "apto", "iptu", "x", {}, numeros=[{"nome": "inscricao_iptu", "valor": "001.002.0003-4"}]))
    assert rep.resolver_titular(con, {"cpf": "52998224725", "nome": "Beatriz"}) == ("pessoa", "ana")  # CPF antes do nome
    assert rep.resolver_titular(con, {"nome": "beatriz"}) == ("pessoa", "bia")
    assert rep.resolver_titular(con, {"inscricao_iptu": "00100200034"}) == ("bem", "apto")
    assert rep.resolver_titular(con, {"endereco": "rua das flores,  10"}) == ("bem", "apto")
    con.execute("insert into pessoa(id, nome, dados) values ('ana2','Ana Clara','{}')")
    assert rep.resolver_titular(con, {"nome": "An"}) is None  # ambígua
    assert rep.resolver_titular(con, {"placa": "ZZZ9Z99"}) is None
    assert rep.resolver_titular(con, {}) is None


def test_tipo_normalizado_e_sem_numero(con):
    pid = _propor(con, _doc(tipo="Apólice Seguro", numero="X1"))
    assert rep.listar_propostas(con)[0]["doc"]["tipo"] == "apolice_seguro"
    assert _erro(rep.decidir, con, pid, "aprovada", "ricardo", AGORA, correcao={"tipo": "apolice 123456"}) == "valor_invalido"
    assert _erro(_propor, con, _doc(tipo="cnh2")) == "valor_invalido"
    assert _erro(_propor, con, _doc(tipo="_x")) == "valor_invalido"
    assert "123456" not in " ".join(r[0] for r in con.execute("select o_que from decisao"))


def test_bens_novos_de_documentos_diferentes_sao_propostas_diferentes(con):
    doc = _doc("bem", None, "apolice", "SEM-NUMERO")
    a = _propor(con, doc, paperless_id=41, bem_novo={"tipo": "outro", "nome": "Coisa A"})
    b = _propor(con, doc, paperless_id=42, bem_novo={"tipo": "outro", "nome": "Coisa B"})
    assert a != b and _propor(con, doc, paperless_id=41, bem_novo={"tipo": "outro", "nome": "Coisa A"}) == a
