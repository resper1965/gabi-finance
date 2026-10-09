import re
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.trabalho import email, frentes

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
RAIZ = Path(__file__).parent.parent.parent / "gabi"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into caixa_email(id, endereco, provedor, estado) values (1,'a@x.com','google','sim')")
    email.ingerir_email(c, 1, lambda cx, cur: ([dict(message_id="<1>", remetente="joao@acme.com.br", assunto="Proposta Atlas", recebido_em="2026-10-09T10:00:00Z", corpo="")], None))
    return c


def _item(con):
    return con.execute("select * from item_email").fetchone()


def test_dominio_reconhece_frente(con):
    fid = frentes.abrir_frente(con, "Acme", "cliente", None, {"dominios": ["acme.com.br"]})
    cands = frentes.reconhecer(con, _item(con))
    assert [c.frente_id for c in cands] == [fid] and "acme.com.br" in cands[0].motivo


def test_palavra_reconhece_frente(con):
    fid = frentes.abrir_frente(con, "Atlas", "projeto", None, {"palavras": ["atlas"]})
    assert [c.frente_id for c in frentes.reconhecer(con, _item(con))] == [fid]


def test_sugestao_de_frente_nao_entra_sem_confirmacao(con):
    fid = frentes.abrir_frente(con, "Acme", "cliente", None, {"dominios": ["acme.com.br"]})
    frentes.sugerir(con, _item(con))
    assert con.execute("select estado from item_frente where frente_id=?", (fid,)).fetchone()[0] == "sugerido"
    assert frentes.itens(con, fid) == []                       # só confirmados aparecem na frente
    frentes.confirmar(con, fid, _item(con)["id"], por="boss")
    assert len(frentes.itens(con, fid)) == 1


def test_confirmar_registra_decisao(con):
    fid = frentes.abrir_frente(con, "Acme", "cliente", None, None)
    frentes.confirmar(con, fid, _item(con)["id"], por="boss")
    assert con.execute("select count(*) from decisao").fetchone()[0] == 1


def test_frente_sem_regra_nao_reconhece_nada(con):
    frentes.abrir_frente(con, "Livre", "interno", None, None)
    assert frentes.reconhecer(con, _item(con)) == []


def test_abrir_frente_nunca_com_nome_fixo_no_codigo():
    fonte = (RAIZ / "trabalho" / "frentes.py").read_text()
    assert not re.search(r"abrir_frente\([^)]*[\"']", fonte)   # nomes vêm do cadastro (R6)


def test_tipo_invalido_e_recusado(con):
    with pytest.raises(ValueError):
        frentes.abrir_frente(con, "X", "qualquer", None, None)
