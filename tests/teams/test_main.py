from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.teams.__main__ import main

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "t.db"
    c = conectar(p)
    migrar(c, MIGR)
    c.close()
    return p


class Falsa:
    def configurada(self):
        return True

    def teams_chats(self, conta):
        return [{"chat_id": "c1", "tipo": "um_a_um", "ultima_em": "2026-10-20T13:00:00+00:00"}]

    def teams_mensagens(self, conta, chat_id, desde):
        return [{"id": "1", "quando": "2026-10-20T13:00:00+00:00", "de_nome": "SEGREDO-NOME", "de_eu": False, "mencoes_eu": False}]


def test_saida_so_contagens(banco, capsys):
    c = conectar(banco)
    c.execute("insert into teams_fonte(conta, estado) values ('a@ness.com.br','sim')")
    c.close()
    assert main(banco, ponte=Falsa()) == 0
    cap = capsys.readouterr()
    assert "chats=1" in cap.out and "novas=1" in cap.out
    assert "SEGREDO" not in cap.out + cap.err
    c = conectar(banco)
    assert c.execute("select status from rodada where fonte='teams'").fetchone()[0] == "ok"


def test_sem_fonte_liberada_rodada_ok(banco, capsys):
    assert main(banco, ponte=Falsa()) == 0
    assert conectar(banco).execute("select status from rodada where fonte='teams'").fetchone()[0] == "ok"


def test_sem_socket_retorna_2(banco, monkeypatch):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert main(banco) == 2


def test_sem_fonte_configurada_retorna_2(banco, monkeypatch):
    monkeypatch.setenv("GABI_FONTES_SOCKET", "/nao/existe.sock")
    assert main(banco) == 2
