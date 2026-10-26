import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.receber_manual import ErroReceber, cancelar, confirmar, propor, registrar, rejeitar, valor_ditado
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


# ---- casamento com o crédito do extrato ----
_n = iter(range(1, 10_000))


def conta(con, estado="sim", tipo="BANK"):
    return con.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values (?,?,?,?,0,?)",
                       (f"c{next(_n)}", "C6", tipo, "C6", estado)).lastrowid


def credito(con, valor=100000, data="2026-10-26", desc="PIX RECEBIDO FAMILIA REIS", cid=None):
    cid = cid or conta(con)
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (?,?,?,?,?, 'posted')",
                       (cid, f"l{next(_n)}", data, valor, desc)).lastrowid


def props(con):
    return [dict(r) for r in con.execute("select * from receber_manual_proposta order by id")]


def test_propoe_valor_mais_ou_menos_1_por_cento_e_pagador_no_descritivo(con):
    r = reg(con, pagador="Família Reis", valor="1000,00", vencimento="2026-10-26")
    a, b, c = credito(con, 100900), credito(con, 100000), credito(con, 101200)
    assert propor(con) == 2
    por = {p["lancamento_id"]: p["confianca"] for p in props(con)}
    assert por == {a: 0.7, b: 1.0}
    assert c not in por and all(p["receber_id"] == r["id"] and p["estado"] == "proposto" for p in props(con))


def test_sem_pagador_no_descritivo_nao_propoe(con):
    reg(con, pagador="Família Reis", valor="1000,00")
    credito(con, 100000, desc="PIX RECEBIDO OUTRA PESSOA")
    assert propor(con) == 0


def test_fora_da_janela_nao_propoe(con):
    reg(con, pagador="Família Reis", valor="1000,00", vencimento="2026-10-26")
    credito(con, data="2026-09-25")  # 31 dias antes
    credito(con, data="2027-01-25")  # 91 dias depois
    assert propor(con) == 0
    dentro = [credito(con, data="2026-09-26"), credito(con, data="2027-01-24")]
    assert propor(con) == 2 and {p["lancamento_id"] for p in props(con)} == set(dentro)


def test_sem_vencimento_a_base_e_o_dia_de_criacao(con):
    reg(con, pagador="Família Reis", valor="1000,00")  # criado em 2026-10-26
    credito(con, data="2026-09-25")
    l = credito(con, data="2026-09-26")
    assert propor(con) == 1 and props(con)[0]["lancamento_id"] == l


def test_negativo_nao_propoe(con):
    reg(con, pagador="Família Reis", valor="-1000,00")
    credito(con, -100000)
    credito(con, 100000)
    assert propor(con) == 0


def test_conta_fora_do_caixa_unico_nao_propoe(con):
    reg(con, pagador="Família Reis", valor="1000,00")
    credito(con, cid=conta(con, estado="nao"))
    credito(con, cid=conta(con, tipo="CREDIT"))
    assert propor(con) == 0


def test_credito_ja_confirmado_para_nota_ou_manual_nao_propoe(con):
    r = reg(con, pagador="Família Reis", valor="1000,00")
    l1, l2, l3 = credito(con), credito(con), credito(con)
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, importado_em, atualizado_em) values ('n1','1','2026-10-01','autorizada',100000,'x','x')")
    nid = "n1"
    con.execute("insert into recebimento_nota(nota_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'m','confirmado','t')", (nid, l1))
    outro = reg(con, pagador="Outro Pagador", valor="1000,00")
    con.execute("insert into receber_manual_proposta(receber_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'m','confirmado','t')", (outro["id"], l2))
    assert propor(con) == 1
    assert [p["lancamento_id"] for p in props(con) if p["receber_id"] == r["id"]] == [l3]


def test_confirmar(con):
    r = reg(con, pagador="Família Reis", valor="1000,00")
    r2 = reg(con, pagador="Família Reis", valor="1000,00")
    l1, l2 = credito(con), credito(con)
    propor(con)
    pid = next(p["id"] for p in props(con) if p["receber_id"] == r["id"] and p["lancamento_id"] == l1)
    confirmar(con, pid, "ricardo")
    row = con.execute("select estado, lancamento_id from receber_manual where id=?", (r["id"],)).fetchone()
    assert (row["estado"], row["lancamento_id"]) == ("recebido", l1)
    est = {(p["receber_id"], p["lancamento_id"]): p["estado"] for p in props(con)}
    assert est == {(r["id"], l1): "confirmado", (r["id"], l2): "rejeitado", (r2["id"], l1): "rejeitado", (r2["id"], l2): "proposto"}
    d = con.execute("select quem, o_que, origem from decisao order by id desc limit 1").fetchone()
    assert d["origem"] == "cobrar" and d["quem"] == "ricardo"
    assert d["o_que"] == f"a receber manual: proposta {pid} confirmada (receber {r['id']}, lançamento {l1})"
    with pytest.raises(ValueError):
        confirmar(con, pid, "ricardo")
    with pytest.raises(LookupError):
        confirmar(con, 999, "ricardo")


def test_rejeitar_nao_repropoe(con):
    reg(con, pagador="Família Reis", valor="1000,00")
    credito(con)
    propor(con)
    pid = props(con)[0]["id"]
    rejeitar(con, pid, "ricardo")
    assert props(con)[0]["estado"] == "rejeitado"
    assert propor(con) == 0 and len(props(con)) == 1
    d = con.execute("select o_que, origem from decisao order by id desc limit 1").fetchone()
    assert d["origem"] == "cobrar" and "FAMILIA" not in d["o_que"].upper()
    with pytest.raises(ValueError):
        rejeitar(con, pid, "ricardo")


def test_cancelado_ou_recebido_nao_propoe(con):
    r = reg(con, pagador="Família Reis", valor="1000,00")
    cancelar(con, r["id"], quem="ricardo", origem="hermes", agora=AGORA)
    r2 = reg(con, pagador="Família Reis", valor="1000,00")
    con.execute("update receber_manual set estado='recebido' where id=?", (r2["id"],))
    credito(con)
    assert propor(con) == 0
