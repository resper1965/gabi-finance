import sqlite3
from pathlib import Path

import pytest

from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent / "migrations"
ESPERADAS = {
    "pessoa", "pet", "empresa", "compromisso_fixo", "matriz_acesso", "allowlist_vip", "acesso",
    "compromisso", "fatura", "conciliacao", "conta_estado", "agenda_estado", "agenda_eventos",
    "memoria", "rodada", "chamada", "decisao", "token_agente", "schema_versao",
}


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_migracao_0001_cria_todas_as_tabelas(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type in ('table')")}
    assert ESPERADAS <= nomes


def test_acesso_rejeita_nivel_invalido(con):
    con.execute("insert into acesso(login, pessoa_id, nivel, criado_em) values ('a@x.com','p1','boss','2026-10-08')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into acesso(login, pessoa_id, nivel, criado_em) values ('b@x.com','p1','x','2026-10-08')")


def _mem(con, chave, texto):
    con.execute("insert into memoria(chave, tipo, texto, origem) values (?, 'memoria', ?, 'teste')", (chave, texto))


def _achar(con, termo):
    return [r[0] for r in con.execute(
        "select m.texto from memoria_fts f join memoria m on m.id=f.rowid where memoria_fts match ?", (termo,))]


def test_memoria_chave_unica(con):
    _mem(con, "1", "a")
    with pytest.raises(sqlite3.IntegrityError):
        _mem(con, "1", "b")


def test_valores_em_centavos_inteiros(con):
    cols = {r["name"]: r["type"] for r in con.execute("pragma table_info(compromisso)")}
    assert cols["valor_centavos"] == "INTEGER"
    assert "valor" not in cols  # R7: nunca float no banco
    assert {r["name"]: r["type"] for r in con.execute("pragma table_info(fatura)")}["total_centavos"] == "INTEGER"
    assert {r["name"]: r["type"] for r in con.execute("pragma table_info(conta_estado)")}["saldo_centavos"] == "INTEGER"


def _msg(con, id_externo):
    con.execute("insert into escuta_msg(id_externo, de, recebida_em) values (?, '+5511', '2026-10-11')", (id_externo,))


def _fonte(con, conta="resper@gmail.com", cal="primary"):
    return con.execute("insert into agenda_fonte(conta, provedor, calendario_id) values (?, 'google', ?)", (conta, cal)).lastrowid


def _evento(con, fonte_id, externo_id="e1"):
    con.execute(
        "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local) "
        "values (?, ?, '2026-10-12T18:00:00+00:00', '2026-10-12T19:00:00+00:00', '2026-10-12', '2026-10-12')", (fonte_id, externo_id))


def test_agenda_tabelas_existem(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"agenda_fonte", "agenda_evento"} <= nomes
    cols = {r["name"] for r in con.execute("pragma table_info(agenda_evento)")}
    assert {"inicio_utc", "fim_utc", "dia_local", "dia_fim_local", "dia_inteiro", "titulo", "link_reuniao",
            "participantes_qtd", "status", "etag", "atualizado_origem", "privado"} <= cols
    assert "participantes" not in cols and "local" not in cols  # privacidade: só a contagem, sem e-mail nem local
    fonte = {r["name"] for r in con.execute("pragma table_info(agenda_fonte)")}
    assert {"conta", "provedor", "calendario_id", "nome", "estado", "auth", "sync_token", "sincronizada_em", "recarga_em", "ultimo_erro"} <= fonte


def test_agenda_fonte_estado_e_provedor_validados(con):
    fid = _fonte(con)
    assert con.execute("select estado, auth, calendario_id from agenda_fonte where id=?", (fid,)).fetchone()[:] == ("a_decidir", "oauth", "primary")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update agenda_fonte set estado='talvez' where id=?", (fid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into agenda_fonte(conta, provedor) values ('x@y.com', 'icloud')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into agenda_fonte(conta, provedor, auth) values ('x@y.com', 'google', 'senha')")
    with pytest.raises(sqlite3.IntegrityError):
        _fonte(con)  # mesma conta + mesmo calendário


def test_agenda_evento_unico_por_fonte_e_externo_id(con):
    f1, f2 = _fonte(con), _fonte(con, "resper@ness.com.br")
    _evento(con, f1, "e1")
    _evento(con, f2, "e1")  # o mesmo id em outra fonte é outro evento
    with pytest.raises(sqlite3.IntegrityError):
        _evento(con, f1, "e1")


def test_agenda_evento_exige_fonte_existente(con):
    with pytest.raises(sqlite3.IntegrityError):
        _evento(con, 999)


def test_0080_normaliza_estados_antigos(tmp_path):
    antigas = tmp_path / "migracoes"
    antigas.mkdir()
    for f in MIGRACOES.glob("*.sql"):
        if f.name < "0080":
            (antigas / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    c = conectar(tmp_path / "g.db")
    migrar(c, antigas)
    for i, e in enumerate(("previsto", "debito_automatico", "aberto", "pago", "atrasado", "a_conferir")):
        c.execute("insert into compromisso(id, origem, nome, vencimento, estado) values (?,?,?,?,?)", (f"c{i}", "linha", f"c{i}", "2026-10-10", e))
    migrar(c, MIGRACOES)
    assert [r[0] for r in c.execute("select estado from compromisso order by id")] == ["aberto", "aberto", "aberto", "pago", "atrasado", "a_conferir"]


def test_receber_manual_0082(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"receber_manual", "receber_manual_proposta"} <= nomes
    ins = "insert into receber_manual(pagador, valor_centavos, criado_em, quem, atualizado_em) values ('X', ?, 'x','r','x')"
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, (0,))
    con.execute(ins, (-100,))
    assert con.execute("select estado from receber_manual").fetchone()[0] == "aberto"
