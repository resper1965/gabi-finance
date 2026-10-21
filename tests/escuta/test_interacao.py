from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import interacao as i

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-21T12:00:00Z"
NUM = "+5511912345678"


@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    k.execute("insert into email_fonte(id, conta, provedor, estado) values (1, 'a@x.com', 'google', 'sim')")
    return k


def _antes(dias: int) -> str:
    return (datetime(2026, 10, 21, 12, tzinfo=timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


_n = [0]


def _email(con, remetente, dias=10, lista=0, classe="normal"):
    _n[0] += 1
    con.execute("insert into email_msg(fonte_id, externo_id, remetente, recebida_em, lista, classe) values (1,?,?,?,?,?)",
                (f"m{_n[0]}", remetente, _antes(dias), lista, classe))


def _wa(con, numero, dias=10):
    _n[0] += 1
    con.execute("insert into escuta_msg(id_externo, de, recebida_em) values (?,?,?)", (f"w{_n[0]}", numero, _antes(dias)))


def _resp(con, endereco, dias):
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (1,?,?)", (endereco, _antes(dias)))


def test_constantes():
    assert (i.JANELA_DIAS, i.PISO_MENSAGENS, i.PISO_RESPOSTAS) == (365, 5, 1)


def test_zero_interacao_nao_passa(con):
    r = i.interacao(con, AGORA, endereco="a@x.com", telefone=NUM)
    assert r == {"mensagens": 0, "respostas": 0} and not i.passa_piso(r)


def test_uma_resposta_passa(con):
    _resp(con, "a@b.com", 30)
    r = i.interacao(con, AGORA, endereco="a@b.com")
    assert r["respostas"] == 1 and i.passa_piso(r)


def test_quatro_mensagens_nao_passam_e_cinco_passam(con):
    for _ in range(4):
        _email(con, "a@b.com")
    assert not i.passa_piso(i.interacao(con, AGORA, endereco="a@b.com"))
    _email(con, "a@b.com")
    r = i.interacao(con, AGORA, endereco="a@b.com")
    assert r["mensagens"] == 5 and i.passa_piso(r)


def test_fora_da_janela_nao_conta(con):
    _resp(con, "a@b.com", 400)
    for _ in range(6):
        _email(con, "a@b.com", dias=366)
    r = i.interacao(con, AGORA, endereco="a@b.com")
    assert r == {"mensagens": 0, "respostas": 0} and not i.passa_piso(r)


def test_remetente_com_nome_e_maiuscula(con):
    _email(con, "Fulano <Fulano@X.COM>")
    assert i.interacao(con, AGORA, endereco="fulano@x.com")["mensagens"] == 1


def test_exclui_noreply_lista_e_notificacao(con):
    for end in ("noreply@x.com", "no-reply@x.com", "donotreply@x.com"):
        for _ in range(10):
            _email(con, end)
        assert i.interacao(con, AGORA, endereco=end)["mensagens"] == 0
    for _ in range(10):
        _email(con, "pessoa@x.com", lista=1)
    assert i.interacao(con, AGORA, endereco="pessoa@x.com")["mensagens"] == 0
    for _ in range(10):
        _email(con, "outro@x.com", classe="lixo")
    assert i.interacao(con, AGORA, endereco="outro@x.com")["mensagens"] == 0


def test_telefone_conta_escuta_msg_e_resposta_e_zero(con):
    for _ in range(4):
        _wa(con, NUM)
    r = i.interacao(con, AGORA, telefone=NUM)
    assert r == {"mensagens": 4, "respostas": 0} and not i.passa_piso(r)
    _wa(con, "5511912345678@s.whatsapp.net")  # mesmo número em outro formato
    r = i.interacao(con, AGORA, telefone=NUM)
    assert r == {"mensagens": 5, "respostas": 0} and i.passa_piso(r)
