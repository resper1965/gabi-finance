"""Ferramentas MCP do escopo `familia`: lista, ficha (com auditoria), vencimentos, contato e proposta de documento.
Consome: gabi.mcp.servidor (criar_mcp), tokens, fixtures de tests/mcp/test_servidor.py."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, criar_mcp, ferramentas_do_token
from gabi.mcp.tokens import emitir
from tests.familia.apoio import doc_pessoa
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar, rpc  # noqa: F401  (fixtures e helpers)

CPF = "52998224725"
PASSAPORTE = "FZ123456"
FAMILIA = {"familia_listar", "familia_consultar", "familia_vencimentos", "familia_atualizar_contato", "familia_propor_documento",
           "documentos_consultar", "documentos_vencimentos", "bens_listar", "familia_registrar_pessoa", "familia_registrar_pet"}


@pytest.fixture
def bancof(banco):
    c = conectar(banco)
    c.execute("update pessoa set excluido_em='2026-10-01T00:00:00Z' where id='p9'")  # a 'Ana' do fixture base sai do cadastro
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps({"apelido": "Aninha", "telefone": "+5511999990000"}),))
    c.execute("insert into pessoa(id, nome, dados) values ('anap','Ana Paula',?)", (json.dumps({"parentesco": "filha"}),))
    c.execute("insert into pessoa(id, nome, dados) values ('bia','Beatriz',?)", (json.dumps({}),))
    doc_pessoa(c, "ana", "cpf", CPF, origem="ricardo")
    doc_pessoa(c, "ana", "passaporte", PASSAPORTE, validade="2027-03-10", origem="ricardo")
    c.close()
    return banco


@pytest.fixture
def tokf(bancof):
    c = conectar(bancof)
    t = {k: emitir(c, k, [k]) for k in ("familia", "fin")}
    c.close()
    return t


@pytest.fixture
def clif(bancof):
    with TestClient(criar_mcp(bancof, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        yield c


def _texto(r) -> str:
    return json.dumps(r, ensure_ascii=False)


def test_escopo_familia_no_hermes_e_nas_ferramentas():
    assert "familia" in ESCOPOS_HERMES
    assert {n for n, e in ESCOPOS_FERRAMENTAS.items() if e == "familia"} == FAMILIA
    assert FAMILIA <= set(ferramentas_do_token(ESCOPOS_HERMES))


def test_token_familia_ve_as_10_ferramentas(clif, tokf):
    nomes = {t["name"] for t in rpc(clif, tokf["familia"], "tools/list").json()["result"]["tools"]}
    assert FAMILIA <= nomes


def test_docstrings_avisam_dado_de_terceiros_e_nunca_em_resumos(clif, tokf):
    desc = {t["name"]: t["description"] for t in rpc(clif, tokf["familia"], "tools/list").json()["result"]["tools"]}
    for n in FAMILIA:
        assert "dado de terceiros" in desc[n], n
    assert "Use só quando o Ricardo perguntar desta pessoa; nunca em resumos" in desc["familia_consultar"]


@pytest.mark.parametrize("nome,args", [("familia_listar", {}), ("familia_consultar", {"pessoa": "Ana"}), ("familia_vencimentos", {}),
                                       ("familia_atualizar_contato", {"pessoa": "Ana", "campo": "apelido", "acao": "definir", "valor": "X"}),
                                       ("familia_propor_documento", {"pessoa": "Ana", "tipo": "rg", "numero": "123"})])
def test_sem_escopo_familia(clif, tokf, bancof, nome, args):
    assert chamar(clif, tokf["fin"], nome, **args)["erro"] == "sem_escopo"
    c = conectar(bancof)
    assert c.execute("select count(*) from familia_proposta").fetchone()[0] == 0
    assert c.execute("select count(*) from pessoa_historico").fetchone()[0] == 0
    assert c.execute("select count(*) from decisao where origem='familia'").fetchone()[0] == 0


def test_listar_sem_numero(clif, tokf):
    r = chamar(clif, tokf["familia"], "familia_listar")
    d = r["dados"]
    assert [p["nome"] for p in d["itens"]] == ["Ana", "Ana Paula", "Beatriz"]
    assert d["itens"][0]["documentos_qtd"] == 2
    assert CPF not in _texto(r) and PASSAPORTE not in _texto(r)


def test_consultar_traz_ficha_e_audita(clif, tokf, bancof):
    d = chamar(clif, tokf["familia"], "familia_consultar", pessoa="aninha")["dados"]
    assert d["id"] == "ana" and {x["numero"] for x in d["documentos"]} == {CPF, PASSAPORTE}
    [a] = conectar(bancof).execute("select quem, o_que, origem from decisao where origem='familia'").fetchall()
    assert a["quem"] == "hermes" and "ana" in a["o_que"] and "cpf" in a["o_que"]
    assert CPF not in a["o_que"] and PASSAPORTE not in a["o_que"]


def test_consultar_ambiguo_traz_candidatos_e_nao_audita(clif, tokf, bancof):
    r = chamar(clif, tokf["familia"], "familia_consultar", pessoa="an")
    assert r["erro"] == "pessoa_ambigua" and "Ana" in r["mensagem"] and "Ana Paula" in r["mensagem"]
    assert conectar(bancof).execute("select count(*) from decisao where origem='familia'").fetchone()[0] == 0


def test_consultar_ninguem(clif, tokf):
    r = chamar(clif, tokf["familia"], "familia_consultar", pessoa="Zé")
    assert r["erro"] == "pessoa_ambigua" and "nenhum" in r["mensagem"]


def test_vencimentos_sem_numero(clif, tokf):
    r = chamar(clif, tokf["familia"], "familia_vencimentos", meses=6)
    d = r["dados"]
    assert d["meses"] == 6 and [(i["pessoa_id"], i["tipo"], i["validade"]) for i in d["itens"]] == [("ana", "passaporte", "2027-03-10")]
    assert CPF not in _texto(r) and PASSAPORTE not in _texto(r)
    assert chamar(clif, tokf["familia"], "familia_vencimentos", meses=4)["dados"]["itens"] == []


def test_vencimentos_meses_invalido(clif, tokf):
    assert chamar(clif, tokf["familia"], "familia_vencimentos", meses=0)["erro"] == "requisicao_invalida"


def test_atualizar_contato_grava_com_quem_hermes(clif, tokf, bancof):
    d = chamar(clif, tokf["familia"], "familia_atualizar_contato", pessoa="Beatriz", campo="emails", acao="adicionar", valor="bia@x.com")["dados"]
    assert d["antes"] == [] and d["depois"] == ["bia@x.com"] and d["historico_id"]
    c = conectar(bancof)
    assert c.execute("select quem from pessoa_historico").fetchone()["quem"] == "hermes"
    assert c.execute("select quem from decisao where origem='familia'").fetchone()["quem"] == "hermes"


def test_atualizar_contato_campo_invalido(clif, tokf):
    r = chamar(clif, tokf["familia"], "familia_atualizar_contato", pessoa="Beatriz", campo="cpf", acao="definir", valor="1")
    assert r["erro"] == "campo_invalido"


def test_propor_documento_pendente_com_link(clif, tokf, bancof):
    c = conectar(bancof)
    c.execute("insert into parametro(chave, valor) values ('painel.url', ?)", (json.dumps("https://painel.x/"),))
    d = chamar(clif, tokf["familia"], "familia_propor_documento", pessoa="Beatriz", tipo="rg", numero="123456", emissor="", validade="")["dados"]
    assert d["estado"] == "pendente" and d["proposta_id"] and d["conferir"] is False and d["link"] == "https://painel.x/#cadastros/documentos"
    p = c.execute("select origem, emissor, validade, paperless_id from familia_proposta").fetchone()
    assert (p["origem"], p["emissor"], p["validade"], p["paperless_id"]) == ("hermes", None, None, None)
    assert c.execute("select count(*) from familia_documento where pessoa_id='bia'").fetchone()[0] == 0  # só propõe


def test_propor_documento_cpf_invalido_conferir_sem_link_sem_parametro(clif, tokf):
    d = chamar(clif, tokf["familia"], "familia_propor_documento", pessoa="Beatriz", tipo="cpf", numero="11122233344")["dados"]
    assert d["conferir"] is True and "link" not in d and "11122233344" not in _texto(d)


def test_propor_documento_identico_ja_existe(clif, tokf):
    d = chamar(clif, tokf["familia"], "familia_propor_documento", pessoa="Ana", tipo="passaporte", numero=PASSAPORTE, validade="2027-03-10")["dados"]
    assert d == {"proposta_id": None, "estado": "ja_existe"}


def test_propor_documento_tipo_invalido_sem_numero_na_mensagem(clif, tokf):
    r = chamar(clif, tokf["familia"], "familia_propor_documento", pessoa="Beatriz", tipo="titulo", numero="987654")
    assert r["erro"] == "campo_invalido" and "987654" not in r["mensagem"]


def test_propor_documento_numero_inteiro_vira_valor_invalido_sem_eco(clif, tokf, bancof):
    r = chamar(clif, tokf["familia"], "familia_propor_documento", pessoa="Beatriz", tipo="cpf", numero=1234567890)
    assert r["erro"] == "valor_invalido" and "1234567890" not in _texto(r)
    assert conectar(bancof).execute("select count(*) from familia_proposta").fetchone()[0] == 0


# ---------------- registrar pessoa e pet (Hermes Onda 1) ----------------
def _reg(cli, token, ferramenta, nome, **args):  # `chamar` já usa `nome` como parâmetro
    res = rpc(cli, token, "tools/call", {"name": ferramenta, "arguments": {"nome": nome, **args}}).json()["result"]
    return json.loads(res["content"][0]["text"]) if res.get("content") else res


NOVAS = {"familia_registrar_pessoa", "familia_registrar_pet"}


def test_registrar_pessoa_nova_e_existente(clif, tokf, bancof):
    c = conectar(bancof)
    c.execute("insert into parametro(chave, valor) values ('painel.url', ?)", (json.dumps("https://painel.x/"),))
    r = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Chafic Esper", parentesco="pai", apelido="Chafa")
    d = r["dados"]
    assert d["criada"] is True and d["pessoa_id"] and d["link"] == "https://painel.x/#cadastros/documentos"
    assert r["desatualizado"] is False
    r2 = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Beatriz", parentesco="amiga")["dados"]
    assert r2["criada"] is False and r2["pessoa_id"] == "bia" and [m["campo"] for m in r2["mudancas"]] == ["parentesco"]
    assert c.execute("select quem from pessoa_historico where campo='criada'").fetchone()["quem"] == "hermes"
    assert c.execute("select status from chamada_mcp where ferramenta='familia_registrar_pessoa'").fetchone()["status"] == "ok"


def test_registrar_pessoa_ambigua_traz_candidatos(clif, tokf, bancof):
    c = conectar(bancof)
    for i, n in (("bs", "Bruno Silva"), ("bc", "Bruno Costa")):
        c.execute("insert into pessoa(id, nome, dados) values (?,?,?)", (i, n, json.dumps({})))
    c.commit()
    r = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Bruno", parentesco="tio")
    assert r["erro"] == "pessoa_ambigua" and "candidatos" in r["mensagem"] and "Bruno Costa" in r["mensagem"]
    assert c.execute("select count(*) from pessoa_historico").fetchone()[0] == 0


def test_registrar_pet_e_listar(clif, tokf, bancof):
    d = _reg(clif, tokf["familia"], "familia_registrar_pet", "Cookie", especie="cachorro", raca="vira-lata", dono="Beatriz")
    assert d["dados"]["criado"] is True and d["dados"]["historico_id"] and d["desatualizado"] is False
    pets = chamar(clif, tokf["familia"], "familia_listar")["dados"]["pets"]
    assert [p["nome"] for p in pets] == ["Cookie"]
    c = conectar(bancof)
    assert c.execute("select status from chamada_mcp where ferramenta='familia_registrar_pet'").fetchone()["status"] == "ok"


@pytest.mark.parametrize("nome,args", [("familia_registrar_pessoa", {"nome": "Zé", "parentesco": "tio"}),
                                       ("familia_registrar_pet", {"nome": "Rex", "especie": "cachorro"})])
def test_registrar_sem_escopo_familia(clif, tokf, bancof, nome, args):
    assert _reg(clif, tokf["fin"], nome, args["nome"], **{k: v for k, v in args.items() if k != "nome"})["erro"] == "sem_escopo"
    assert conectar(bancof).execute("select count(*) from pessoa_historico").fetchone()[0] == 0


def test_docstrings_das_novas(clif, tokf):
    desc = {t["name"]: t["description"] for t in rpc(clif, tokf["familia"], "tools/list").json()["result"]["tools"]}
    for n in NOVAS:
        assert "dado de terceiros" in desc[n] and "só diga que anotou depois do ok desta ferramenta" in desc[n], n
    assert "Nome ambíguo volta com candidatos: pergunte qual" in desc["familia_registrar_pessoa"]


def test_registrar_pessoa_devolve_nome_e_titular_vira_pergunta(clif, tokf, bancof):
    c = conectar(bancof)
    c.execute("insert into pessoa(id, nome, papel, dados) values ('eu','Ricardo Chafic Esper','titular','{}')")
    c.commit()
    d = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Sandra Maria Esper", parentesco="tia")["dados"]
    assert (d["nome"], d["nome_completo"]) == ("Sandra", "Sandra Maria Esper")
    r = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Ricardo Esper", parentesco="eu")
    assert r["erro"] == "pessoa_ambigua" and "candidatos: Ricardo Chafic Esper" in r["mensagem"]
    assert c.execute("select dados from pessoa where id='eu'").fetchone()["dados"] == "{}"


def test_candidatos_e_listar_mostram_nome_completo(clif, tokf, bancof):
    for n in ("Sandra Maria Esper", "Sandra Lima"):
        _reg(clif, tokf["familia"], "familia_registrar_pessoa", n, parentesco="tia")
    r = _reg(clif, tokf["familia"], "familia_registrar_pessoa", "Sandra", parentesco="tia")
    assert r["erro"] == "pessoa_ambigua" and "Sandra (Sandra Maria Esper)" in r["mensagem"] and "Sandra (Sandra Lima)" in r["mensagem"]
    itens = chamar(clif, tokf["familia"], "familia_listar")["dados"]["itens"]
    assert {i["nome_completo"] for i in itens if i["nome"] == "Sandra"} == {"Sandra Maria Esper", "Sandra Lima"}
