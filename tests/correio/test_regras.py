import json
from pathlib import Path

import pytest

from gabi.correio import regras
from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com"):
    return con.execute("insert into email_fonte(conta, provedor, estado) values (?, 'google', 'sim')", (conta,)).lastrowid


def _pessoa(con, id_, canais, excluido=None):
    con.execute("insert into pessoa(id, nome, dados, excluido_em) values (?,?,?,?)", (id_, id_, json.dumps({"canais": canais}), excluido))


@pytest.mark.parametrize("texto,esperado", [
    ("ana@x.com", "ana@x.com"), ("Ana Silva <ANA.Silva@Empresa.COM>", "ana.silva@empresa.com"), ('"Silva, Ana" <ana@x.com>', "ana@x.com"),
    ("sem endereco", None), ("", None), (None, None), (3, None), ("a@b", None), ("a b@x.com", None)])
def test_endereco_extrai_de_nome_e_angulos(texto, esperado):
    assert regras.endereco(texto) == esperado


def test_protegido_por_pessoa_com_canal_de_email(con):
    f = _fonte(con)
    _pessoa(con, "p1", ["whatsapp:+5511999990000", "email:Ana@X.com"])
    assert regras.protegido(con, f, "ana@x.com") == "aprovado"
    assert regras.protegido(con, f, "Ana <ANA@x.com>") == "aprovado"
    assert regras.protegido(con, f, "outra@x.com") is None


def test_protegido_por_pessoa_com_emails_no_cadastro(con):
    f = _fonte(con)
    con.execute("insert into pessoa(id, nome, dados) values ('p9','p9',?)", (json.dumps({"emails": ["Bia@X.com"]}),))
    assert regras.protegido(con, f, "Bia <bia@x.com>") == "aprovado"
    assert regras.protegido(con, f, "outra@x.com") is None


def test_pessoa_excluida_nao_protege(con):
    f = _fonte(con)
    _pessoa(con, "p1", ["email:ana@x.com"], excluido="2026-10-01T00:00:00+00:00")
    assert regras.protegido(con, f, "ana@x.com") is None


def test_protegido_por_vip_e_por_respondido(con):
    f, g = _fonte(con), _fonte(con, "b@x.com")
    con.execute("insert into parametro(chave, valor) values ('email.vips', ?)", (json.dumps(["Chefe@Ionic.com", "invalido", 3]),))
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?, 'bia@x.com', '2026-10-01T00:00:00+00:00')", (f,))
    assert regras.protegido(con, f, "chefe@ionic.com") == "vip" and regras.protegido(con, g, "chefe@ionic.com") == "vip"
    assert regras.protegido(con, f, "BIA@x.com") == "respondido"
    assert regras.protegido(con, g, "bia@x.com") is None  # "já respondi" vale na conta em que respondi
    assert regras.protegido(con, f, "promo@loja.com") is None


def test_sem_remetente_valido_nunca_vira_candidato(con):
    f = _fonte(con)
    assert regras.protegido(con, f, "") == "sem_remetente" and regras.protegido(con, f, None) == "sem_remetente"
    assert regras.protegido(con, f, "texto sem endereco") == "sem_remetente"


def test_vips_corrompido_nao_derruba(con):
    f = _fonte(con)
    con.execute("insert into parametro(chave, valor) values ('email.vips', 'nao-e-json')")
    assert regras.protegido(con, f, "x@y.com") is None


@pytest.mark.parametrize("assunto,trecho,remetente", [
    ("Sua fatura vence em 3 dias", "", "cobranca@banco.com"), ("Boleto disponível", "", "x@y.com"), ("Re: contrato", "", "x@y.com"),
    ("Aviso", "o vencimento é amanhã", "x@y.com"), ("AVISO IMPORTANTE", "Nota Fiscal emitida", "x@y.com"), ("Intimação judicial", "", "x@y.com"),
    ("Seu código de verificação", "", "x@y.com"), ("COBRANÇA em aberto", "", "x@y.com"), ("cobranca em aberto", "", "x@y.com"),  # acento e caixa não contam
    ("Oi", "", "dae@sefaz.gov")])
def test_texto_com_palavra_protegida_nunca_vira_candidato(con, assunto, trecho, remetente):
    assert regras.texto_protegido(con, remetente, assunto, trecho) == "palavra"


@pytest.mark.parametrize("assunto,trecho,remetente", [
    ("Oferta imperdível: 50% de desconto", "só hoje", "promo@loja.com"), ("Newsletter da semana", "as novidades", "news@blog.com"), ("", "", ""), (None, None, None)])
def test_texto_comum_de_promocao_nao_e_protegido(con, assunto, trecho, remetente):
    assert regras.texto_protegido(con, remetente, assunto, trecho) is None


def test_palavras_protegidas_vem_do_parametro_e_o_dono_pode_trocar_a_lista(con):
    con.execute("insert into parametro(chave, valor) values ('email.palavras_protegidas', ?)", (json.dumps(["Pedido", "  ", 3]),))
    assert regras.texto_protegido(con, "x@y.com", "Seu PEDIDO saiu", "") == "palavra"
    assert regras.texto_protegido(con, "x@y.com", "Sua fatura", "") is None  # a lista do dono substitui a padrão


def test_parametro_de_palavras_corrompido_cai_na_lista_padrao(con):
    con.execute("insert into parametro(chave, valor) values ('email.palavras_protegidas', 'nao-e-json')")
    assert regras.texto_protegido(con, "x@y.com", "Sua fatura", "") == "palavra"
