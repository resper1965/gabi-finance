from pathlib import Path

import pytest

from gabi.agenda.__main__ import main
from gabi.db import conectar, migrar
from gabi.fontes.google_agenda import ResultadoEventos
from gabi.fontes.google_oauth import ErroGoogleOAuth

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "t.db"
    c = conectar(p)
    migrar(c, MIGR)
    c.close()
    return p


def _fonte(banco, conta, estado="sim"):
    c = conectar(banco)
    c.execute("insert into agenda_fonte(conta, provedor, estado) values (?, 'google', ?)", (conta, estado))
    c.close()


def _ev(i, titulo):
    return {"externo_id": i, "inicio": {"dateTime": "2026-10-13T13:00:00-03:00"}, "fim": {"dateTime": "2026-10-13T14:00:00-03:00"},
            "titulo": titulo, "link_reuniao": None, "participantes_qtd": 1, "status": "confirmed", "etag": None, "atualizado_origem": None, "privado": False}


def test_main_sincroniza_com_cliente_falso_e_imprime_so_contagens(banco, capsys):
    _fonte(banco, "a@x.com")
    rc = main(banco, listar=lambda c, cal, t, j: ResultadoEventos([_ev("1", "SEGREDO-TITULO"), _ev("2", "OUTRO-SEGREDO")], [], "T", False))
    saida = capsys.readouterr()
    assert rc == 0 and "gravados=2" in saida.out
    assert "SEGREDO" not in saida.out + saida.err
    assert conectar(banco).execute("select count(*) from agenda_evento").fetchone()[0] == 2


def test_main_sem_fonte_sim_sai_0(banco, capsys):
    _fonte(banco, "a@x.com", estado="a_decidir")
    assert main(banco, listar=lambda *a: pytest.fail("não deveria listar")) == 0
    assert "fontes=0" in capsys.readouterr().out


def test_main_todas_falham_sai_1(banco, capsys):
    _fonte(banco, "a@x.com"); _fonte(banco, "b@x.com")

    def listar(*a):
        raise ErroGoogleOAuth("calendar.events.list -> 500")
    assert main(banco, listar=listar) == 1
    assert "falhou" in capsys.readouterr().err


def test_main_conta_nao_autorizada_nao_conta_como_falha_geral(banco):
    _fonte(banco, "a@x.com"); _fonte(banco, "b@x.com")

    def listar(conta, *a):
        raise ErroGoogleOAuth(f"conta não autorizada: {conta}")
    assert main(banco, listar=listar) == 0


def test_main_uma_ok_e_outra_falha_sai_0(banco):
    _fonte(banco, "ruim@x.com"); _fonte(banco, "boa@x.com")

    def listar(conta, *a):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("calendar.events.list -> 500")
        return ResultadoEventos([], [], "T", False)
    assert main(banco, listar=listar) == 0


def test_main_sem_socket_sai_2(banco, monkeypatch, capsys):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert main(banco) == 2 and "GABI_FONTES_SOCKET" in capsys.readouterr().err
