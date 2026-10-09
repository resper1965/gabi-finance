import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.trabalho import email

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into caixa_email(id, endereco, provedor, estado) values (1,'a@x.com','google','sim')")
    c.execute("insert into caixa_email(id, endereco, provedor, estado) values (2,'b@x.com','graph','sim')")
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps({"emails": ["ana@cliente.com"]}),))
    return c


def _msg(mid="<1@x>", **kw):
    base = dict(message_id=mid, remetente="fulano@x.com", assunto="Oi", recebido_em="2026-10-09T10:00:00Z", corpo="texto " * 200)
    base.update(kw)
    return base


def _fonte(*msgs, token="t1"):
    return lambda caixa, cursor: (list(msgs), token)


def test_item_guarda_so_cabecalho_e_trecho(con):
    email.ingerir_email(con, 1, _fonte(_msg()))
    cols = {r[1] for r in con.execute("pragma table_info(item_email)")}
    assert "corpo" not in cols
    trecho = con.execute("select trecho from item_email").fetchone()[0]
    assert 0 < len(trecho) <= email.TAM_TRECHO


def test_message_id_duplicado_nao_duplica_nem_entre_caixas(con):
    email.ingerir_email(con, 1, _fonte(_msg("<m@x>")))
    r = email.ingerir_email(con, 2, _fonte(_msg("<m@x>")))   # mesmo e-mail chegando por Google e Graph (migração da ness)
    assert con.execute("select count(*) from item_email").fetchone()[0] == 1
    assert r.duplicados == 1 and r.novos == 0


def test_cursor_avanca_so_depois_de_gravar(con):
    email.ingerir_email(con, 1, _fonte(_msg(), token="t9"))
    assert con.execute("select cursor from caixa_email where id=1").fetchone()[0] == "t9"


def test_caixa_nao_liberada_nao_e_lida(con):
    con.execute("update caixa_email set estado='a_decidir' where id=1")
    r = email.ingerir_email(con, 1, _fonte(_msg()))
    assert r.novos == 0 and con.execute("select count(*) from item_email").fetchone()[0] == 0


def test_ler_a_partir_de_ignora_o_antigo(con):
    con.execute("update caixa_email set ler_a_partir_de='2026-10-01T00:00:00Z' where id=1")
    email.ingerir_email(con, 1, _fonte(_msg("<a>", recebido_em="2026-09-01T00:00:00Z"), _msg("<b>")))
    assert [r[0] for r in con.execute("select message_id from item_email")] == ["<b>"]


def test_relevante_sempre_traz_motivo(con):
    con.execute("insert into parametro(chave, valor) values ('email_palavras_relevantes', ?)", (json.dumps(["boleto"]),))
    for m in (_msg("<1>", remetente="ana@cliente.com"), _msg("<2>", assunto="Boleto vence amanhã"), _msg("<3>")):
        email.ingerir_email(con, 1, _fonte(m))
    rows = con.execute("select relevante, motivo from item_email order by id").fetchall()
    assert all(r["motivo"] for r in rows)
    assert [r["relevante"] for r in rows] == [1, 1, 0]


def test_palavras_relevantes_vem_do_cadastro_nao_do_codigo(con):
    con.execute("insert into parametro(chave, valor) values ('email_palavras_relevantes', ?)", (json.dumps(["urgente"]),))
    email.ingerir_email(con, 1, _fonte(_msg("<1>", assunto="Boleto vence amanhã"), _msg("<2>", assunto="URGENTE: contrato")))
    rel = {r["message_id"]: r["relevante"] for r in con.execute("select message_id, relevante from item_email")}
    assert rel == {"<1>": 0, "<2>": 1}


def test_expurgo_sem_regra_ligada_nao_apaga_nada(con):
    email.ingerir_email(con, 1, _fonte(_msg(assunto="Promoção")))
    con.execute("insert into regra_expurgo(assunto_contem, ligada, criada_em) values ('Promoção', 0, '2026-10-09')")
    assert email.expurgo_sugerido(con) == []
    assert con.execute("select count(*) from item_email where estado='novo'").fetchone()[0] == 1


def test_expurgo_com_regra_ligada_so_sugere(con):
    email.ingerir_email(con, 1, _fonte(_msg(assunto="Promoção")))
    con.execute("insert into regra_expurgo(assunto_contem, ligada, criada_em) values ('Promoção', 1, '2026-10-09')")
    ids = email.expurgo_sugerido(con)
    assert len(ids) == 1
    assert con.execute("select estado from item_email").fetchone()[0] == "novo"   # nada foi apagado


def test_conflito_gera_proposta_nao_envia(con):
    for i, (a, b) in enumerate([("2026-10-10T14:00:00", "2026-10-10T15:00:00"), ("2026-10-10T14:30:00", "2026-10-10T15:30:00")]):
        con.execute("insert into evento(caixa_id, externo_id, inicio, fim, titulo) values (1,?,?,?,?)", (f"e{i}", a, b, f"Reunião {i}"))
    achados = email.conflitos(con, "2026-10-10T00:00:00", "2026-10-11T00:00:00")
    assert len(achados) == 1
    c = achados[0]
    assert c.sugestao_inicio >= "2026-10-10T15:30:00"
    assert not hasattr(email, "enviar")


def test_eventos_e_tarefas_sao_idempotentes(con):
    from gabi.trabalho import agenda, tarefas
    ev = [{"externo_id": "e1", "inicio": "2026-10-10T10:00:00", "fim": "2026-10-10T11:00:00", "titulo": "A", "participantes": ["x@y.com"]}]
    agenda.ingerir_eventos(con, 1, lambda c, cur: (ev, None))
    ev[0]["titulo"] = "A2"
    agenda.ingerir_eventos(con, 1, lambda c, cur: (ev, None))
    assert con.execute("select count(*), max(titulo) from evento").fetchone()[:] == (1, "A2")
    t = [{"externo_id": "t1", "titulo": "X", "prazo": None, "concluida": False}]
    tarefas.ingerir_tarefas(con, "graph", t)
    t[0]["concluida"] = True
    tarefas.ingerir_tarefas(con, "graph", t)
    assert con.execute("select count(*), max(estado) from tarefa").fetchone()[:] == (1, "concluida")
