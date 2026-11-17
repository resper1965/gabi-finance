import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.decisoes import ErroDecisao, abertas, criar_pergunta, expirar, responder

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
T0 = "2026-10-16T12:00:00+00:00"
T1 = "2026-10-16T13:00:00+00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.sqlite")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(id, externo_id, apelido, estado) values (10, 'x10', 'Conta Dez', 'a_decidir')")
    return c


def _opcoes(conta=10):
    return [{"n": 1, "rotulo": "Tirar do caixa", "efeito": "marcar_conta_nao", "parametros": {"conta_id": conta}},
            {"n": 2, "rotulo": "Manter", "efeito": "registrar_nota"}]


def test_criar_e_listar_abertas(con):
    pid = criar_pergunta(con, "conta", "Conta Dez entra no caixa?", "sem uso há 30 dias", _opcoes(), "claude", T0)
    lista = abertas(con)
    assert [p["id"] for p in lista] == [pid] and lista[0]["opcoes"][0]["n"] == 1 and lista[0]["estado"] == "aberta"


def test_efeito_fora_da_lista_fechada_e_recusado(con):
    with pytest.raises(ErroDecisao):
        criar_pergunta(con, "x", "t", None, [{"n": 1, "rotulo": "a", "efeito": "rm_rf"}], "claude", T0)


def test_numeracao_invalida_e_conta_inexistente_sao_recusadas(con):
    with pytest.raises(ErroDecisao):
        criar_pergunta(con, "x", "t", None, [{"n": 2, "rotulo": "a", "efeito": "registrar_nota"}], "claude", T0)
    with pytest.raises(ErroDecisao):
        criar_pergunta(con, "x", "t", None, _opcoes(conta=999), "claude", T0)
    with pytest.raises(ErroDecisao):
        criar_pergunta(con, "x", "t", None, [], "claude", T0)


def test_responder_aplica_efeito_e_grava_decisao_como_dele(con):
    pid = criar_pergunta(con, "conta", "Conta Dez entra no caixa?", None, _opcoes(), "claude", T0)
    r = responder(con, pid, 1, "ricardo", T1)
    assert r["estado"] == "respondida" and r["escolha"] == 1 and r["ja_respondida"] is False
    assert con.execute("select estado from conta where id=10").fetchone()[0] == "nao"
    d = con.execute("select quem, o_que, origem from decisao").fetchall()
    assert len(d) == 1 and d[0]["quem"] == "ricardo" and d[0]["origem"] == "canal" and "Tirar do caixa" in d[0]["o_que"]
    assert abertas(con) == []


def test_opcao_so_registrar_nao_mexe_em_nada(con):
    pid = criar_pergunta(con, "conta", "t", None, _opcoes(), "claude", T0)
    responder(con, pid, 2, "ricardo", T1)
    assert con.execute("select estado from conta where id=10").fetchone()[0] == "a_decidir"
    assert con.execute("select count(*) from decisao").fetchone()[0] == 1


def test_resposta_so_uma_vez_e_idempotente_na_mesma_escolha(con):
    pid = criar_pergunta(con, "conta", "t", None, _opcoes(), "claude", T0)
    responder(con, pid, 1, "ricardo", T1)
    again = responder(con, pid, 1, "ricardo", T1)
    assert again["ja_respondida"] is True and con.execute("select count(*) from decisao").fetchone()[0] == 1
    with pytest.raises(ErroDecisao) as e:
        responder(con, pid, 2, "ricardo", T1)
    assert e.value.codigo == "ja_respondida" and con.execute("select estado from conta where id=10").fetchone()[0] == "nao"


def test_numero_invalido_e_pergunta_inexistente(con):
    pid = criar_pergunta(con, "conta", "t", None, _opcoes(), "claude", T0)
    for n in (0, 3, -1, "1", None, True):
        with pytest.raises(ErroDecisao):
            responder(con, pid, n, "ricardo", T1)
    with pytest.raises(ErroDecisao) as e:
        responder(con, 999, 1, "ricardo", T1)
    assert e.value.codigo == "nao_encontrada"
    assert con.execute("select estado from pergunta where id=?", (pid,)).fetchone()[0] == "aberta"


def test_efeito_que_falha_desfaz_tudo(con):
    pid = criar_pergunta(con, "conta", "t", None, _opcoes(), "claude", T0)
    con.execute("update conta set excluido_em='2026-10-01' where id=10")  # a conta sumiu depois da pergunta
    with pytest.raises(ErroDecisao):
        responder(con, pid, 1, "ricardo", T1)
    assert con.execute("select estado from pergunta where id=?", (pid,)).fetchone()[0] == "aberta"
    assert con.execute("select count(*) from decisao").fetchone()[0] == 0


def test_expirar_so_as_abertas_antigas_e_expirada_nao_responde(con):
    a = criar_pergunta(con, "x", "velha", None, _opcoes(), "claude", "2026-09-01T00:00:00+00:00")
    b = criar_pergunta(con, "x", "nova", None, _opcoes(), "claude", T0)
    assert expirar(con, "2026-10-01T00:00:00+00:00") == 1
    assert [p["id"] for p in abertas(con)] == [b]
    with pytest.raises(ErroDecisao) as e:
        responder(con, a, 1, "ricardo", T1)
    assert e.value.codigo == "expirada"


def test_opcoes_sao_json_valido_no_banco(con):
    pid = criar_pergunta(con, "x", "t", None, _opcoes(), "claude", T0)
    assert json.loads(con.execute("select opcoes from pergunta where id=?", (pid,)).fetchone()[0])[1]["efeito"] == "registrar_nota"
