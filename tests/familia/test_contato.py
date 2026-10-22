"""Contato com histórico e desfazer.
Consome: gabi.familia.contato, migrações."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.familia import contato
from gabi.familia.fichas import ErroFamilia

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)",
              (json.dumps({"telefone": "+5511999990000", "enderecos": [{"texto": "Rua A"}, "Rua B"]}),))
    return c


def _dados(con):
    return json.loads(con.execute("select dados from pessoa where id='ana'").fetchone()["dados"])


def _erro(con, *a):
    with pytest.raises(ErroFamilia) as e:
        contato.atualizar(con, "ana", *a, "boss", AGORA)
    return e.value.codigo


def test_adicionar_telefone_grava_e_historia(con):
    r = contato.atualizar(con, "ana", "telefones", "adicionar", "(11) 98888-7777", "boss", AGORA)
    assert r["antes"] == [] and r["depois"] == ["+5511988887777"]
    d = _dados(con)
    assert d["telefones"] == ["+5511988887777"] and d["telefone"] == "+5511999990000"
    h = contato.historico(con, "ana")
    assert len(h) == 1 and h[0]["campo"] == "telefones" and h[0]["id"] == r["historico_id"]


def test_invalidos(con):
    assert _erro(con, "telefones", "adicionar", "abc") == "valor_invalido"
    assert _erro(con, "emails", "adicionar", "sem-arroba") == "valor_invalido"
    assert _erro(con, "cpf", "definir", "1") == "campo_invalido"
    assert _erro(con, "telefones", "remover", "(11) 98888-7777") == "valor_invalido"
    assert _erro(con, "nascimento", "definir", "01/02/2000") == "valor_invalido"
    assert _erro(con, "telefones", "definir", "x") == "requisicao_invalida"
    assert _erro(con, "apelido", "adicionar", "x") == "requisicao_invalida"
    assert _erro(con, "telefones", "remover", "+5511999990000") == "valor_invalido"  # só no campo legado
    assert contato.historico(con) == []


def test_pessoa_inexistente(con):
    with pytest.raises(ErroFamilia) as e:
        contato.atualizar(con, "zzz", "apelido", "definir", "x", "boss", AGORA)
    assert e.value.codigo == "nao_encontrado"


def test_limite_de_dez(con):
    for i in range(10):
        contato.atualizar(con, "ana", "emails", "adicionar", f"a{i}@x.com", "boss", AGORA)
    assert _erro(con, "emails", "adicionar", "a10@x.com") == "valor_invalido"
    assert len(_dados(con)["emails"]) == 10


def test_enderecos_existentes_preservados_e_remover(con):
    contato.atualizar(con, "ana", "enderecos", "adicionar", "Rua C", "boss", AGORA)
    assert _dados(con)["enderecos"] == [{"texto": "Rua A"}, "Rua B", "Rua C"]
    contato.atualizar(con, "ana", "enderecos", "remover", "Rua A", "boss", AGORA)
    contato.atualizar(con, "ana", "enderecos", "remover", "Rua B", "boss", AGORA)
    assert _dados(con)["enderecos"] == ["Rua C"]


def test_definir_texto(con):
    r = contato.atualizar(con, "ana", "apelido", "definir", " Aninha ", "boss", AGORA)
    assert r["antes"] is None and r["depois"] == "Aninha"
    assert contato.atualizar(con, "ana", "nascimento", "definir", "2000-01-02", "boss", AGORA)["depois"] == "2000-01-02"


def test_desfazer_restaura_e_marca(con):
    r = contato.atualizar(con, "ana", "telefones", "adicionar", "(11) 98888-7777", "boss", AGORA)
    d = contato.desfazer(con, r["historico_id"], "boss", AGORA)
    assert "telefones" not in _dados(con) and d["depois"] == []
    h = contato.historico(con, "ana")
    assert len(h) == 2 and h[1]["desfeito_em"] and not h[0]["desfeito_em"]
    with pytest.raises(ErroFamilia) as e:  # já desfeito
        contato.desfazer(con, r["historico_id"], "boss", AGORA)
    assert e.value.codigo == "conflito"


def test_desfazer_apos_outra_mudanca_da_conflito(con):
    r1 = contato.atualizar(con, "ana", "apelido", "definir", "A", "boss", AGORA)
    contato.atualizar(con, "ana", "apelido", "definir", "B", "boss", AGORA)
    with pytest.raises(ErroFamilia) as e:
        contato.desfazer(con, r1["historico_id"], "boss", AGORA)
    assert e.value.codigo == "conflito"
    assert _dados(con)["apelido"] == "B"
    assert contato.historico(con, "ana")[-1]["desfeito_em"] is None


def test_auditoria_sem_valor(con):
    r = contato.atualizar(con, "ana", "telefones", "adicionar", "(11) 98888-7777", "boss", AGORA)
    contato.desfazer(con, r["historico_id"], "boss", AGORA)
    linhas = [x["o_que"] for x in con.execute("select o_que from decisao where origem='familia'")]
    assert len(linhas) == 2 and all("ana" in t and "telefones" in t for t in linhas)
    assert not any("98888" in t for t in linhas)
