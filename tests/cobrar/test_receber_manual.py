import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.receber_manual import ErroReceber, cancelar, registrar, valor_ditado
from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def reg(con, **kw):
    base = dict(pagador="ORM Reis", valor="1500,00", quem="ricardo", origem="hermes", agora=AGORA)
    return registrar(con, **{**base, **kw})


def codigo(f, *a, **kw):
    with pytest.raises(ErroReceber) as e:
        f(*a, **kw)
    return e.value.codigo


def test_valor_ditado():
    assert codigo(valor_ditado, "1.500") == "valor_invalido"
    assert valor_ditado("R$ 1.500,00") == 150000
    assert valor_ditado("1500") == 150000
    assert valor_ditado("-300,00") == -30000
    assert codigo(valor_ditado, "0") == "valor_invalido"
    assert codigo(valor_ditado, "10000000,01") == "valor_invalido"
    assert codigo(valor_ditado, "abc") == "valor_invalido"


def test_registrar_grava_e_audita_sem_dado(con):
    r = reg(con, vencimento="", conta=" ", observacao="")
    assert r["valor_centavos"] == 150000 and r["estado"] == "aberto"
    assert r["vencimento"] is None and r["conta"] is None and r["observacao"] is None
    d = con.execute("select * from decisao").fetchone()
    assert d["o_que"] == f"a receber manual {r['id']} registrado" and d["origem"] == "hermes"
    assert "ORM" not in d["o_que"] and "1500" not in d["o_que"]


def test_vencimento_invalido(con):
    assert codigo(reg, con, vencimento="31/10") == "valor_invalido"
    assert reg(con, vencimento="2026-10-31")["vencimento"] == "2026-10-31"


def test_pagador_vazio(con):
    assert codigo(reg, con, pagador="  ") == "valor_invalido"


def test_cancelar(con):
    r = reg(con)
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('c','C6','BANK','C6',0,'sim')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (1,'x','2026-10-20',150000,'Pix','posted')")
    con.execute("insert into receber_manual_proposta(receber_id, lancamento_id, confianca, motivo, criado_em) values (?,1,1.0,'m','x')", (r["id"],))
    c = cancelar(con, r["id"], quem="ricardo", origem="hermes", agora=AGORA)
    assert c["estado"] == "cancelado"
    assert con.execute("select estado from receber_manual_proposta").fetchone()[0] == "rejeitado"
    assert con.execute("select o_que from decisao order by id desc").fetchone()[0] == f"a receber manual {r['id']} cancelado"
    assert codigo(cancelar, con, r["id"], quem="ricardo", origem="hermes", agora=AGORA) == "conflito"
    assert codigo(cancelar, con, 999, quem="ricardo", origem="hermes", agora=AGORA) == "nao_encontrado"


def test_cancelar_recebido_e_conflito(con):
    r = reg(con)
    con.execute("update receber_manual set estado='recebido' where id=?", (r["id"],))
    assert codigo(cancelar, con, r["id"], quem="ricardo", origem="hermes", agora=AGORA) == "conflito"
