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


def _cru(con, bruto):
    con.execute("update pessoa set dados=? where id='ana'", (bruto,))


@pytest.mark.parametrize("bruto", ["{quebrado", "[1,2]", '"texto"', json.dumps({"telefones": "+5511"}),
                                   json.dumps({"emails": {"a": 1}, "x": 1})])
def test_dados_corrompidos_nao_sao_sobrescritos(con, bruto):
    _cru(con, bruto)
    lista_ruim = "telefones" in bruto or "emails" in bruto
    for campo, acao, v in (("apelido", "definir", "A"), ("telefones", "adicionar", "(11) 98888-7777"),
                           ("emails", "adicionar", "a@x.com")):
        if lista_ruim and (campo == "apelido" or campo not in bruto):
            continue  # só o campo de lista corrompido é recusado; os outros gravariam sem perder nada
        assert _erro(con, campo, acao, v) == "requisicao_invalida"
        assert con.execute("select dados from pessoa where id='ana'").fetchone()["dados"] == bruto
    assert contato.historico(con) == []


def test_dados_nulo_ou_vazio_vira_vazio(con):
    for bruto in (None, ""):
        _cru(con, bruto)
        contato.atualizar(con, "ana", "apelido", "definir", "A", "boss", AGORA)
        assert _dados(con) == {"apelido": "A"}


def test_remover_normaliza_itens_existentes(con):
    _cru(con, json.dumps({"telefones": ["(11) 98888-7777"], "emails": ["A@X.com "]}))
    contato.atualizar(con, "ana", "telefones", "remover", "+5511988887777", "boss", AGORA)
    contato.atualizar(con, "ana", "emails", "remover", "a@x.com", "boss", AGORA)
    assert _dados(con) == {}


def test_nascimento_data_inexistente(con):
    assert _erro(con, "nascimento", "definir", "2000-13-45") == "valor_invalido"


def test_atomicidade(con, monkeypatch):
    antes = con.execute("select dados from pessoa where id='ana'").fetchone()["dados"]

    def falha(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(contato, "_historico", falha)
    with pytest.raises(RuntimeError):
        contato.atualizar(con, "ana", "apelido", "definir", "A", "boss", AGORA)
    assert con.execute("select dados from pessoa where id='ana'").fetchone()["dados"] == antes
    assert con.execute("select count(*) n from decisao where origem='familia'").fetchone()["n"] == 0


# ---- endereço em dict (forma do yaml) ----------------------------------------------------------------------------

END = {"tipo": "residencial", "logradouro": "Rua Exemplo, 10", "bairro": "Centro", "cidade": "São Paulo", "uf": "SP",
       "cep": "01000-000", "observacao": "portaria"}


def _com_endereco_dict(con):
    d = _dados(con)
    d["enderecos"] = [dict(END), "Rua B"]
    con.execute("update pessoa set dados=? where id='ana'", (json.dumps(d, ensure_ascii=False),))


def test_formatar_endereco_pula_partes_vazias():
    assert contato.formatar_endereco(END) == "Rua Exemplo, 10, Centro, São Paulo/SP, 01000-000"
    assert contato.formatar_endereco({"logradouro": "Rua X", "bairro": "", "cidade": None, "uf": "RJ"}) == "Rua X, RJ"


def test_remover_endereco_dict_pelo_texto_formatado(con):
    _com_endereco_dict(con)
    r = contato.atualizar(con, "ana", "enderecos", "remover", " Rua Exemplo, 10, Centro, São Paulo/SP, 01000-000 ", "boss", AGORA)
    assert r["depois"] == ["Rua B"] and _dados(con)["enderecos"] == ["Rua B"]


def test_adicionar_endereco_igual_ao_dict_e_duplicado(con):
    _com_endereco_dict(con)
    assert _erro(con, "enderecos", "adicionar", "Rua Exemplo, 10, Centro, São Paulo/SP, 01000-000") == "valor_invalido"


def test_observacao_e_falecido(con):
    contato.atualizar(con, "ana", "observacao", "definir", " mora fora ", "boss", AGORA)
    r = contato.atualizar(con, "ana", "falecido", "definir", True, "boss", AGORA)
    d = _dados(con)
    assert d["observacao"] == "mora fora" and d["falecido"] is True
    assert _erro(con, "falecido", "definir", "sim") == "valor_invalido"
    contato.desfazer(con, r["historico_id"], "boss", AGORA)
    assert "falecido" not in _dados(con)
