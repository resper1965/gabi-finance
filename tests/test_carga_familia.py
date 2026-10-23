"""Carga da família: familia.yaml (fonte principal) e OCR do Paperless (complemento), tudo com dados de exemplo.
Consome: tools.carga_familia, gabi.familia, migrações. Nunca lê o familia.yaml real, o banco de produção nem o Paperless."""
import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from gabi.db import conectar, migrar
from gabi.familia import contato, documentos
from tools import carga_familia as carga

MIGRACOES = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 23, 12, 0, tzinfo=dt.timezone.utc)
CPF_OK = "529.982.247-25"
CPF_OK2 = "111.444.777-35"
CPF_RUIM = "529.982.247-26"

YAML = """
pessoas:
  - id: ana
    nome: Ana
    apelido: Aninha
    telefone: "+55 11 90000-0001"
    nascimento: 1980-02-03
    enderecos: ["Rua Exemplo, 1"]
    documentos:
      - {tipo: CPF, numero: "529.982.247-25"}
      - {tipo: Passaporte, numero: AB123456, autoridade_emissora: PF, expedicao: 2021-05-01, validade: 2031-05-01}
      - {tipo: Carteira de Motorista, numero: "12345678901", validade: "31/12/2030"}
      - {tipo: Identidade, numero: None}
      - {tipo: Título de eleitor, numero: "pendente"}
  - id: bia
    nome: Bia Paula
    documentos:
      - {tipo: cpf, numero: "529.982.247-26"}
      - {tipo: passaporte, numero: CD654321, emissor: PF}
  - id: fantasma
    nome: Ninguém
    documentos: [{tipo: cpf, numero: "111.444.777-35"}]
pets:
  - {id: rex, nome: Rex, especie: cachorro}
  - {id: tom, nome: Tom, especie: gato}
empresas:
  - id: emp
    nome: Empresa Exemplo
    documentos: [{tipo: NIF, numero: "PT500000000"}]
    dados_bancarios: {banco: Exemplo, iban: PT50000000000000000000000}
obrigacoes:
  - {id: o1, descricao: Pensão, pessoa: ana}
matriz_de_acesso: {linhas: []}
assistente: {nome: x}
documento: {x: 1}
"""


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    ana = {"id": "ana", "nome": "Ana", "telefone": "+5511900000001",
           "documentos": [{"tipo": "CPF", "numero": "***.***.***-25"}, {"tipo": "Passaporte", "numero": "AA****56"}]}
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps(ana),))
    c.execute("insert into pessoa(id, nome, dados) values ('bia','Bia Paula',?)", (json.dumps({"apelido": "Bia"}),))
    c.execute("insert into pessoa(id, nome, dados) values ('anap','Ana Clara',?)", (json.dumps({}),))
    for tipo, numero in (("cpf", "***.***.***-25"), ("passaporte", "AA****56")):
        c.execute("insert into pessoa_documento(pessoa_id, tipo, numero, origem) values ('ana',?,?,'legado')", (tipo, numero))
    c.execute("insert into pet(id, nome, especie, dados) values ('rex','Rex','cachorro',?)",
              (json.dumps({"id": "rex", "nome": "Rex", "especie": "cachorro", "origem": "x"}),))
    c.execute("insert into pet(id, nome, especie, dados) values ('tom','Tom','cachorro',?)",
              (json.dumps({"id": "tom", "nome": "Tom", "especie": "cachorro"}),))
    c.execute("insert into empresa(id, nome, dados) values ('emp','Empresa Exemplo',?)",
              (json.dumps({"id": "emp", "documentos": [{"tipo": "NIF", "numero": "PT*****0000"}], "dados_bancarios": {"banco": "Exemplo"}}),))
    c.execute("insert into compromisso_fixo(id, descricao, pessoa_id, dados) values ('o1','Pensão','ana',?)",
              (json.dumps({"id": "o1", "descricao": "Pensão", "pessoa": "ana"}),))
    return c


def _dados():
    return yaml.safe_load(YAML)


def _props(con, pessoa="ana"):
    return {r["tipo"]: dict(r) for r in con.execute("select * from pessoa_proposta where pessoa_id=? order by id", (pessoa,))}


def _contar(con, tabela):
    return con.execute(f"select count(*) from {tabela}").fetchone()[0]


# ---- etapa yaml --------------------------------------------------------------------------------------------------

def test_yaml_liga_por_id_e_conta_sem_cadastro(con):
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    assert r["pessoas_lidas"] == 3 and r["sem_cadastro"] == 1 and r["empresas_lidas"] == 1
    assert con.execute("select count(*) from pessoa where id='fantasma'").fetchone()[0] == 0
    assert all(p["origem"] == "carga" for p in con.execute("select origem from pessoa_proposta"))


def test_yaml_documentos_normaliza_tipo_e_campos(con):
    carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    p = _props(con)
    assert set(p) == {"cpf", "passaporte", "cnh"}  # "None" e "pendente" não viram proposta
    assert p["passaporte"]["emissor"] == "PF" and p["passaporte"]["emissao"] == "2021-05-01"
    assert p["passaporte"]["validade"] == "2031-05-01" and p["passaporte"]["conferir"] == 0
    assert p["cnh"]["validade"] is None  # "31/12/2030" não é YYYY-MM-DD: descartada
    assert p["cnh"]["conferir"] == 1  # cnh sem validade


def test_yaml_substitui_mascarado(con):
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    p = _props(con)
    mascarados = {d["tipo"]: d["id"] for d in con.execute("select id, tipo from pessoa_documento where pessoa_id='ana'")}
    assert p["cpf"]["documento_id"] == mascarados["cpf"] and p["cpf"]["conferir"] == 0
    assert p["passaporte"]["documento_id"] == mascarados["passaporte"]
    assert r["substituem_mascarado"] == 2
    documentos.decidir(con, p["cpf"]["id"], "aprovada", "ricardo", AGORA)
    assert _contar(con, "pessoa_documento") == 2
    assert con.execute("select numero from pessoa_documento where id=?", (mascarados["cpf"],)).fetchone()[0] == CPF_OK


def test_yaml_cpf_sem_dv_e_passaporte_sem_validade_conferir(con):
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    p = _props(con, "bia")
    assert p["cpf"]["conferir"] == 1 and p["passaporte"]["conferir"] == 1
    assert r["conferir"] == 3 and r["propostas"] == 5


def test_yaml_data_iso_em_texto_e_invalida(con):
    d = _dados()
    d["pessoas"][1]["documentos"][1]["validade"] = "2031-02-30"
    d["pessoas"][1]["documentos"][1]["expedicao"] = "2021-01-15"
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    p = _props(con, "bia")["passaporte"]
    assert p["validade"] is None and p["emissao"] == "2021-01-15"
    assert r["datas_descartadas"] >= 2


def test_yaml_documento_igual_ao_ativo_nao_gera_proposta(con):
    con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, emissor, origem) values ('bia','passaporte','CD654321','PF','ricardo')")
    carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    assert "passaporte" not in _props(con, "bia")


# ---- contato -----------------------------------------------------------------------------------------------------

def test_contato_grava_em_campo_vazio_e_nunca_editado(con):
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    d = json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])
    assert d["apelido"] == "Aninha" and d["nascimento"] == "1980-02-03" and d["enderecos"] == ["Rua Exemplo, 1"]
    assert d["telefone"] == "+5511900000001"  # igual (normalizado): não grava
    h = {x["campo"]: x for x in contato.historico(con, "ana")}
    assert set(h) == {"apelido", "nascimento", "enderecos"} and all(x["quem"] == "carga" for x in h.values())
    assert r["contatos_gravados"] == 3


def test_contato_telefone_diferente_nunca_editado_grava_e_desfaz(con):
    d = _dados()
    d["pessoas"][0]["telefone"] = "+55 11 98888-7777"
    carga.carregar_yaml(con, d, AGORA, aplicar=True)
    h = [x for x in contato.historico(con, "ana") if x["campo"] == "telefone"][0]
    assert h["antes"] == "+5511900000001" and h["depois"] == "+5511988887777"
    contato.desfazer(con, h["id"], "ricardo", AGORA)
    assert json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])["telefone"] == "+5511900000001"


def test_contato_editado_nao_muda_e_conta_divergencia(con):
    contato.atualizar(con, "ana", "apelido", "definir", "Nana", "ricardo", AGORA)
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    d = json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])
    assert d["apelido"] == "Nana" and r["divergencias"] == 1
    assert len([x for x in contato.historico(con, "ana") if x["campo"] == "apelido"]) == 1


def test_contato_valor_igual_nao_grava(con):
    con.execute("update pessoa set dados=? where id='bia'", (json.dumps({"apelido": "Bia"}),))
    d = _dados()
    d["pessoas"][1]["apelido"] = "Bia"
    carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert contato.historico(con, "bia") == []


# ---- empresa, pets, obrigações -----------------------------------------------------------------------------------

def test_empresa_atualiza_e_grava_decisao_sem_valor(con):
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    d = json.loads(con.execute("select dados from empresa where id='emp'").fetchone()[0])
    assert d["dados_bancarios"]["iban"].startswith("PT50") and d["documentos"][0]["numero"] == "PT500000000"
    textos = [x["o_que"] for x in con.execute("select o_que from decisao where origem='familia' and quem='carga'")]
    assert "carga atualizou dados_bancarios da empresa emp" in textos and "carga atualizou documentos da empresa emp" in textos
    assert not any("PT50" in t or "PT500000000" in t for t in textos)
    assert r["empresa_campos"] == 2


def test_pets_e_obrigacoes_so_conferem(con):
    antes = [tuple(x) for x in con.execute("select * from pet order by id")]
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    assert [tuple(x) for x in con.execute("select * from pet order by id")] == antes
    assert r["pets_divergentes"] == 1 and r["obrigacoes_divergentes"] == 0


# ---- idempotência e simulação ------------------------------------------------------------------------------------

def test_rodar_duas_vezes_nao_duplica(con):
    carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    n = (_contar(con, "pessoa_proposta"), _contar(con, "pessoa_historico"), _contar(con, "decisao"))
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    assert (_contar(con, "pessoa_proposta"), _contar(con, "pessoa_historico"), _contar(con, "decisao")) == n
    assert r["propostas"] == 0 and r["contatos_gravados"] == 0 and r["empresa_campos"] == 0


def test_sem_aplicar_nada_e_gravado(con):
    antes = {t: _contar(con, t) for t in ("pessoa_proposta", "pessoa_historico", "decisao")}
    dados_antes = [tuple(x) for x in con.execute("select id, dados from pessoa union all select id, dados from empresa")]
    r = carga.carregar_yaml(con, _dados(), AGORA, aplicar=False)
    assert r["propostas"] == 5 and r["contatos_gravados"] == 3
    assert {t: _contar(con, t) for t in antes} == antes
    assert [tuple(x) for x in con.execute("select id, dados from pessoa union all select id, dados from empresa")] == dados_antes


def _arquivos(tmp_path, con):
    y = tmp_path / "familia.yaml"
    y.write_text(YAML, encoding="utf-8")
    con.close()
    return y, tmp_path / "g.db"


def test_main_simula_e_aplica_sem_mostrar_numero(tmp_path, con, capsys):
    y, banco = _arquivos(tmp_path, con)
    assert carga.main(["--yaml", str(y), "--banco", str(banco), "--sem-ocr"]) == 0
    saida = capsys.readouterr()
    c = conectar(banco)
    assert c.execute("select count(*) from pessoa_proposta").fetchone()[0] == 0
    assert carga.main(["--yaml", str(y), "--banco", str(banco), "--sem-ocr", "--aplicar"]) == 0
    saida2 = capsys.readouterr()
    assert {r[0] for r in c.execute("select origem from pessoa_proposta")} == {"carga"}
    tudo = saida.out + saida.err + saida2.out + saida2.err
    assert "propostas: 5" in tudo
    for segredo in ("529", "AB123456", "CD654321", "12345678901", "PT50", "Aninha", "Rua Exemplo", "98888"):
        assert segredo not in tudo


# ---- OCR ---------------------------------------------------------------------------------------------------------

def test_extrair_cpf_com_e_sem_dv():
    itens = {i["numero"]: i for i in carga.extrair(f"Nome: Fulano CPF {CPF_OK} e outro CPF: {CPF_RUIM}") if i["tipo"] == "cpf"}
    assert itens[CPF_OK]["conferir"] is True  # mais de um candidato
    assert itens[CPF_RUIM]["conferir"] is True
    so = carga.extrair(f"CPF {CPF_OK}")
    assert so == [{"tipo": "cpf", "numero": CPF_OK, "emissao": None, "validade": None, "conferir": False}]
    assert carga.extrair(f"CPF {CPF_RUIM}")[0]["conferir"] is True


def test_extrair_passaporte_com_validade_mes_por_extenso():
    ocr = "REPUBLICA FEDERATIVA DO BRASIL PASSAPORTE\nNo AB123456\nData de validade / Date of expiry\n15 JAN/JAN 2031"
    [p] = carga.extrair(ocr)
    assert p == {"tipo": "passaporte", "numero": "AB123456", "emissao": None, "validade": "2031-01-15", "conferir": False}
    [p] = carga.extrair("Passport AB123456 valid until 3 março 2030")
    assert p["validade"] == "2030-03-03"


def test_extrair_data_br_e_ambiguas():
    [p] = carga.extrair("Passaporte AB123456 validade 25/03/2031")
    assert p["validade"] == "2031-03-25" and p["conferir"] is False
    [p] = carga.extrair("Passaporte AB123456 validade 01/02/2030")
    assert p["validade"] == "2030-02-01" and p["conferir"] is True  # dd/mm × mm/dd
    [p] = carga.extrair("Passaporte AB123456 validade 25/03/2031 expira 20/04/2032")
    assert p["conferir"] is True


def test_extrair_rg_e_cnh():
    itens = {i["tipo"]: i for i in carga.extrair(
        f"CARTEIRA NACIONAL DE HABILITAÇÃO Nº REGISTRO 12345678901 VALIDADE 20/11/2030 CPF {CPF_OK}")}
    assert itens["cnh"]["numero"] == "12345678901" and itens["cnh"]["validade"] == "2030-11-20"
    assert itens["cpf"]["numero"] == CPF_OK and itens["cpf"]["conferir"] is False
    [rg] = carga.extrair("REGISTRO GERAL RG 12.345.678-X")
    assert rg["tipo"] == "rg" and rg["numero"] == "12.345.678-X"


def test_ligar_pelo_nome_no_titulo_ou_ocr(con):
    assert carga.ligar(con, "Passaporte Bia Paula", "") == "bia"
    assert carga.ligar(con, "doc 1", "Titular: ANA CLARA SOUZA") == "anap"  # "Ana" sozinha não casa com "Ana Clara"
    assert carga.ligar(con, "Passaporte da Ana", "") == "ana"
    assert carga.ligar(con, "Ana e Bia", "") is None
    assert carga.ligar(con, "Sem nome", "nada") is None


class PaperlessFalso:
    def __init__(self, docs):
        self._docs = docs
        self.chamadas = []

    def docs(self, **kw):
        self.chamadas.append(kw)
        termo = kw.get("query", "").lower()
        return [d for d in self._docs if termo in (d["title"] + " " + d["content"]).lower()]

    def texto(self, id):
        return next(d["content"] for d in self._docs if d["id"] == id)


def test_ocr_completa_campo_vazio_e_diverge(con):
    carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    papel = PaperlessFalso([
        {"id": 11, "title": "Passaporte Bia Paula", "content": "PASSAPORTE CD654321 Date of expiry 10 MAR 2032"},
        {"id": 12, "title": "CPF Bia Paula", "content": f"CPF {CPF_OK2}"},
        {"id": 13, "title": "Contrato", "content": f"CPF {CPF_OK}"},
    ])
    r = carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    p = _props(con, "bia")
    assert p["passaporte"]["validade"] == "2032-03-10" and p["passaporte"]["paperless_id"] == 11
    yaml_cpf = con.execute("select * from pessoa_proposta where pessoa_id='bia' and tipo='cpf' and numero=?", (CPF_RUIM,)).fetchone()
    assert yaml_cpf["estado"] == "pendente"  # a proposta do yaml fica; a do OCR, diferente, sai conferir=1
    ocr_cpf = con.execute("select * from pessoa_proposta where pessoa_id='bia' and tipo='cpf' and numero=?", (CPF_OK2,)).fetchone()
    assert ocr_cpf["conferir"] == 1 and ocr_cpf["paperless_id"] == 12 and ocr_cpf["origem"] == "carga"
    assert r["paperless_lidos"] == 3 and r["ocr_sem_pessoa"] == 1
    assert {c["query"] for c in papel.chamadas} == set(carga.TERMOS)


def test_ocr_divergente_do_ativo_conferir_e_igual_nao_propoe(con):
    con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, validade, origem) values ('bia','passaporte','CD654321','2032-03-10','ricardo')")
    con.execute("insert into pessoa_documento(pessoa_id, tipo, numero, validade, paperless_id, origem) values ('bia','cnh','12345678901','2030-01-01',9,'ricardo')")
    papel = PaperlessFalso([
        {"id": 21, "title": "Passaporte Bia Paula", "content": "PASSAPORTE CD654321 validade 11/04/2033"},
        {"id": 22, "title": "CNH Bia Paula", "content": "registro 12345678901 validade 01/01/2030"},
    ])
    carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    p = _props(con, "bia")
    assert p["passaporte"]["validade"] == "2033-04-11" and p["passaporte"]["conferir"] == 1
    assert "cnh" not in p  # igual ao ativo (o paperless_id já existe)


def test_ocr_sem_aplicar_nao_grava_e_duas_vezes_nao_duplica(con):
    papel = PaperlessFalso([{"id": 31, "title": "Passaporte Bia Paula", "content": "PASSAPORTE EF111222 validade 25/03/2031"}])
    r = carga.carregar_ocr(con, papel, AGORA, aplicar=False)
    assert r["propostas"] == 1 and _contar(con, "pessoa_proposta") == 0
    carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    r = carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    assert _contar(con, "pessoa_proposta") == 1 and r["propostas"] == 0


def test_main_com_ocr_falso_so_contagens(tmp_path, con, capsys):
    y, banco = _arquivos(tmp_path, con)
    papel = PaperlessFalso([{"id": 41, "title": "Passaporte Bia Paula", "content": "PASSAPORTE CD654321 validade 25/03/2031"}])
    assert carga.main(["--yaml", str(y), "--banco", str(banco), "--aplicar"], paperless=papel) == 0
    saida = capsys.readouterr()
    assert "paperless_lidos: 1" in saida.out and "propostas_completadas: 1" in saida.out
    for segredo in ("CD654321", "2031", "Bia"):
        assert segredo not in saida.out + saida.err


# ---- fix round 1: formas reais -----------------------------------------------------------------------------------

END_A = {"tipo": "residencial", "logradouro": "Rua Exemplo, 10, apto 2", "bairro": "Centro", "cidade": "São Paulo", "uf": "SP",
         "cep": None}
END_LONGO = {"tipo": "residencial", "logradouro": "Avenida de Exemplo Comprida, 1234, bloco B, apartamento 56",
             "bairro": "Jardim Exemplo", "cidade": "Rio de Janeiro", "uf": "RJ", "cep": "20000-000",
             "observacao": "Portaria 24h; entregas com o zelador. " * 8}


def _com_enderecos(con, pid, enderecos):
    d = json.loads(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()[0])
    d["enderecos"] = enderecos
    con.execute("update pessoa set dados=? where id=?", (json.dumps(d, ensure_ascii=False), pid))


def test_endereco_dict_igual_nao_grava(con):
    _com_enderecos(con, "ana", [END_A])
    d = _dados()
    d["pessoas"][0]["enderecos"] = [dict(END_A)]
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert not [h for h in contato.historico(con, "ana") if h["campo"] == "enderecos"]
    assert r["contatos_gravados"] == 2  # só apelido e nascimento


def test_endereco_dict_mudado_grava_inteiro_com_observacao_longa(con):
    _com_enderecos(con, "ana", [END_A])
    d = _dados()
    d["pessoas"][0]["enderecos"] = [dict(END_LONGO)]
    carga.carregar_yaml(con, d, AGORA, aplicar=True)
    atual = json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])["enderecos"]
    assert atual == [END_LONGO] and len(END_LONGO["observacao"]) > 200
    [h] = [h for h in contato.historico(con, "ana") if h["campo"] == "enderecos"]
    assert h["antes"] == [END_A] and h["depois"] == [END_LONGO] and h["quem"] == "carga"
    contato.desfazer(con, h["id"], "ricardo", AGORA)
    assert json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])["enderecos"] == [END_A]



def test_endereco_campo_grande_demais_e_descartado(con):
    d = _dados()
    d["pessoas"][0]["enderecos"] = [{**END_A, "observacao": "x" * 2001}]
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert r["contatos_descartados"] == 1
    assert "enderecos" not in json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])


def test_historico_da_propria_carga_nao_conta_como_editado(con):
    carga.carregar_yaml(con, _dados(), AGORA, aplicar=True)
    d = _dados()
    d["pessoas"][0]["apelido"] = "Ana Corrigida"
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])["apelido"] == "Ana Corrigida"
    assert r["divergencias"] == 0 and r["contatos_gravados"] == 1


def test_telefone_com_historico_em_telefones_conta_divergencia(con):
    contato.atualizar(con, "ana", "telefones", "adicionar", "+55 11 97777-6666", "hermes", AGORA)
    d = _dados()
    d["pessoas"][0]["telefone"] = "+55 11 98888-7777"
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()[0])["telefone"] == "+5511900000001"
    assert r["divergencias"] == 1


def test_pets_e_obrigacoes_comparam_so_chaves_comuns_e_sem_cadastro_separado(con):
    d = _dados()
    d["pets"].append({"id": "nina", "nome": "Nina"})
    d["pets"][0]["vacinas"] = ["v8"]  # chave que o brain não tem: não é divergência
    d["obrigacoes"].append({"id": "o9", "descricao": "Outra"})
    d["empresas"].append({"id": "emp9", "nome": "Outra"})
    r = carga.carregar_yaml(con, d, AGORA, aplicar=True)
    assert r["pets_divergentes"] == 1 and r["obrigacoes_divergentes"] == 0
    assert (r["sem_cadastro"], r["pets_sem_cadastro"], r["obrigacoes_sem_cadastro"], r["empresas_sem_cadastro"]) == (1, 1, 1, 1)


def test_ocr_ligado_so_pelo_corpo_sai_conferir(con):
    papel = PaperlessFalso([
        {"id": 51, "title": "Digitalização 51", "content": "PASSAPORTE EF111222 Bia Paula validade 25/03/2031"},
        {"id": 52, "title": "Passaporte Bia Paula", "content": "PASSAPORTE GH333444 validade 25/03/2031"},
    ])
    carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    c = {r["numero"]: r["conferir"] for r in con.execute("select numero, conferir from pessoa_proposta where pessoa_id='bia'")}
    assert c["EF111222"] == 1
    assert c["GH333444"] == 1  # outra proposta aberta do mesmo tipo: diverge


def test_ocr_ligado_so_pelo_corpo_sozinho(con):
    papel = PaperlessFalso([{"id": 53, "title": "Scan", "content": "PASSAPORTE EF111222 Bia Paula validade 25/03/2031"}])
    carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    assert con.execute("select conferir from pessoa_proposta where numero='EF111222'").fetchone()[0] == 1
    papel = PaperlessFalso([{"id": 54, "title": "Passaporte Bia Paula", "content": "PASSAPORTE JK555666 validade 25/03/2031"}])
    con.execute("delete from pessoa_proposta")
    carga.carregar_ocr(con, papel, AGORA, aplicar=True)
    assert con.execute("select conferir from pessoa_proposta where numero='JK555666'").fetchone()[0] == 0


def test_main_erro_na_etapa_yaml_so_texto_fixo(tmp_path, con, capsys, monkeypatch):
    y, banco = _arquivos(tmp_path, con)

    def explode(*a, **k):
        raise RuntimeError("AB123456 vazou")
    monkeypatch.setattr(carga, "_carregar_yaml", explode)
    assert carga.main(["--yaml", str(y), "--banco", str(banco), "--sem-ocr"]) == 1
    saida = capsys.readouterr()
    assert "RuntimeError" in saida.err and "AB123456" not in saida.out + saida.err
