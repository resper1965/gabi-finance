"""Lixeira compartilhada (planejar/aplicar/marcar). Consome: gabi.correio.lixeira."""
import datetime as dt
from pathlib import Path

from gabi.correio import lixeira
from gabi.db import conectar, migrar
from gabi.fontes.google_oauth import ErroGoogleOAuth

AGORA = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)


def _banco(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values ('a@x.com','google','sim',1)")
    c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values ('b@ness.com','graph','sim',0)")
    return c


def _msg(c, fonte, ext, estado="classificada", classe="lixo"):
    return c.execute("insert into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, classe, prioridade, motivo, estado, atualizado_em) "
                     "values (?,?,?,'r@x.com','Assunto',?,?,0,'m',?,?)", (fonte, ext, ext, "2026-10-25T10:00:00Z", classe, estado, "2026-10-25T10:00:00Z")).lastrowid


class Ponte:
    def __init__(self, res=None, erro=None):
        self.chamadas, self.res, self.erro = [], res, erro

    def lixeira(self, conta, ids):
        self.chamadas.append((conta, list(ids)))
        if self.erro:
            raise self.erro
        return self.res if self.res is not None else {i: "ok" for i in ids}


def test_planejar_por_conta(tmp_path):
    c = _banco(tmp_path)
    a, b = _msg(c, 1, "e1"), _msg(c, 1, "e2")
    lotes, falhas, ja = lixeira.planejar(c, [a, b, a], so_lixo=True)
    assert lotes == {("google", "a@x.com", 1): [(a, "e1"), (b, "e2")]} and falhas == [] and ja == []
    assert lixeira.planejar(c, [999], so_lixo=True)[1] == [{"id": 999, "codigo": "nao_encontrado"}]


def test_conta_sem_lixeira(tmp_path):
    c = _banco(tmp_path)
    m = _msg(c, 2, "n1")
    lotes, falhas, _ = lixeira.planejar(c, [m], so_lixo=False)
    assert lotes == {} and falhas == [{"id": m, "codigo": "conta_sem_lixeira"}]
    c.execute("update email_fonte set estado='nao' where id=2")
    assert lixeira.planejar(c, [m], so_lixo=False)[1] == [{"id": m, "codigo": "conta_desligada"}]


def test_ja_na_lixeira(tmp_path):
    c = _banco(tmp_path)
    m = _msg(c, 1, "e1", estado="na_lixeira")
    assert lixeira.planejar(c, [m], so_lixo=False) == ({}, [], [m])


def test_so_lixo_recusa_importante(tmp_path):
    c = _banco(tmp_path)
    imp, res, nova = _msg(c, 1, "i", classe="importante"), _msg(c, 1, "r", estado="restaurada"), _msg(c, 1, "n", estado="nova", classe=None)
    assert lixeira.planejar(c, [imp], so_lixo=True)[1] == [{"id": imp, "codigo": "nao_triada"}]
    lotes, falhas, _ = lixeira.planejar(c, [imp, res, nova], so_lixo=False)
    assert [i for i, _ in lotes[("google", "a@x.com", 1)]] == [imp, res] and falhas == [{"id": nova, "codigo": "nao_triada"}]


def test_aplicar_e_marcar(tmp_path):
    c = _banco(tmp_path)
    a, b = _msg(c, 1, "e1"), _msg(c, 1, "e2")
    ok, f = lixeira.aplicar(Ponte(res={"e1": "ok", "e2": "erro"}), "a@x.com", [(a, "e1"), (b, "e2")])
    assert ok == [a] and f == [{"id": b, "codigo": "fonte_indisponivel"}]
    assert lixeira.marcar(c, ok, AGORA) == 1 and lixeira.marcar(c, ok, AGORA) == 0
    assert c.execute("select estado from email_msg where id=?", (a,)).fetchone()[0] == "na_lixeira"


def test_ponte_falha_nada_marcado(tmp_path):
    c = _banco(tmp_path)
    a = _msg(c, 1, "e1")
    ok, f = lixeira.aplicar(Ponte(erro=ErroGoogleOAuth("token de a@x.com venceu")), "a@x.com", [(a, "e1")])
    assert ok == [] and f == [{"id": a, "codigo": "fonte_indisponivel"}]
    assert c.execute("select estado from email_msg where id=?", (a,)).fetchone()[0] == "classificada"
