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


# ---------------- correio (0026) ----------------
def _fonte_correio(con, conta="a@x.com"):
    return con.execute("insert into email_fonte(conta, provedor) values (?, 'google')", (conta,)).lastrowid


def _msg_correio(con, fonte, ext="m1", **extra):
    colunas = {"fonte_id": fonte, "externo_id": ext, "thread_id": "t1", "remetente": "r@x.com", "assunto": "oi", "recebida_em": "2026-10-12T10:00:00+00:00", **extra}
    return con.execute(f"insert into email_msg({','.join(colunas)}) values ({','.join('?' * len(colunas))})", list(colunas.values())).lastrowid


def test_correio_tem_as_tres_tabelas_com_os_checks(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"email_fonte", "email_msg", "email_respondido"} <= nomes
    f = _fonte_correio(con)
    linha = con.execute("select estado, lixeira from email_fonte where id=?", (f,)).fetchone()
    assert tuple(linha) == ("a_decidir", 0)  # nada é lido nem movido até o dono liberar
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into email_fonte(conta, provedor) values ('b@x.com', 'imap')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into email_fonte(conta, provedor, estado) values ('c@x.com', 'google', 'talvez')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into email_fonte(conta, provedor, lixeira) values ('d@x.com', 'google', 2)")
    with pytest.raises(sqlite3.IntegrityError):
        _fonte_correio(con)  # conta única
    m = _msg_correio(con, f)
    assert tuple(con.execute("select estado, tentativas, lista, classe from email_msg where id=?", (m,)).fetchone()) == ("nova", 0, 0, None)
    with pytest.raises(sqlite3.IntegrityError):
        _msg_correio(con, f)  # (fonte_id, externo_id) único
    for coluna, valor in (("classe", "spam"), ("estado", "apagada"), ("prioridade", 4), ("lista", 2)):
        with pytest.raises(sqlite3.IntegrityError):
            _msg_correio(con, f, ext=f"x{coluna}", **{coluna: valor})
    for classe in ("normal", "importante", "emergencial", "lixo"):
        _msg_correio(con, f, ext=f"c-{classe}", classe=classe, prioridade=3)
    for estado in ("nova", "classificada", "alertada", "na_lixeira", "restaurada", "falhou"):
        _msg_correio(con, f, ext=f"e-{estado}", estado=estado)


def test_correio_respondido_tem_chave_composta_e_exige_a_fonte(con):
    f = _fonte_correio(con)
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?, 'r@x.com', '2026-10-12T10:00:00+00:00')", (f,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into email_respondido(fonte_id, endereco, em) values (?, 'r@x.com', '2026-10-13T10:00:00+00:00')", (f,))
    con.execute("pragma foreign_keys=on")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into email_respondido(fonte_id, endereco, em) values (999, 'z@x.com', '2026-10-12T10:00:00+00:00')")


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


def test_documentos_0081_tabelas_e_checks(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"bem", "documento", "documento_numero", "documento_data", "documento_proposta", "documento_leitura"} <= nomes
    con.execute("insert into bem(id, tipo, nome) values ('carro','veiculo','Carro')")
    assert con.execute("select dados from bem").fetchone()[0] == "{}"
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into bem(id, tipo, nome) values ('x','barco','X')")
    d = con.execute("insert into documento(titular_tipo, titular_id, tipo, origem) values ('bem','carro','crlv','leitura')").lastrowid
    assert con.execute("select pais from documento where id=?", (d,)).fetchone()[0] == "BR"
    for titular, origem in (("pet", "leitura"), ("bem", "email")):
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("insert into documento(titular_tipo, titular_id, tipo, origem) values (?, 'carro', 'crlv', ?)", (titular, origem))
    con.execute("insert into documento_data(documento_id, tipo, data) values (?, 'validade', '2030-01-01')", (d,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into documento_data(documento_id, tipo, data) values (?, 'validade', '2031-01-01')", (d,))  # uma por tipo
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into documento_data(documento_id, tipo, data) values (?, 'prazo', '2031-01-01')", (d,))
    doc = '{"titular_tipo":"bem","titular_id":"carro"}'
    con.execute("insert into documento_proposta(doc, origem) values (?, 'leitura')", (doc,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into documento_proposta(doc, origem) values ('nao json', 'leitura')")
    for col, val in (("estado", "talvez"), ("origem", "email"), ("conferir", 2)):
        cols = {"doc": doc, "origem": "leitura", col: val}
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(f"insert into documento_proposta({','.join(cols)}) values ({','.join('?' * len(cols))})", tuple(cols.values()))
    con.execute("insert into documento_leitura(paperless_id, estado, lido_em) values (1, 'lido', '2026-10-23T05:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into documento_leitura(paperless_id, estado, lido_em) values (2, 'quebrado', '2026-10-23T05:00:00Z')")


def test_receber_manual_0082(con):
    nomes = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"receber_manual", "receber_manual_proposta"} <= nomes
    ins = "insert into receber_manual(pagador, valor_centavos, criado_em, quem, atualizado_em) values ('X', ?, 'x','r','x')"
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, (0,))
    con.execute(ins, (-100,))
    assert con.execute("select estado from receber_manual").fetchone()[0] == "aberto"
