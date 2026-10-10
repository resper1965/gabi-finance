import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.caixa import registrar_remetente_visto
from gabi.escuta.remetentes import aprovar, avisar_novo, bloquear, estado_remetente, fila, ignorar

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-11T10:00:00"
N = "+5511912345678"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _msg(con, texto="segredo", numero=N, anexo="a.pdf"):
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, texto, anexo_caminho, estado) values (?,?,?,?,?, 'retida')",
                (f"x{con.execute('select count(*) from escuta_msg').fetchone()[0]}", numero, AGORA, texto, anexo))


def test_pessoa_com_canal_mas_sem_aprovacao_e_pendente(con):
    con.execute("insert into pessoa(id, nome, dados) values ('p1','Fulano', ?)",
                (json.dumps({"canais": [f"whatsapp:{N}"], "pode_pedir": True}),))
    registrar_remetente_visto(con, N, AGORA)
    assert estado_remetente(con, N) == ("pendente", None)
    con.execute("update pessoa set dados=? where id='p1'", (json.dumps({"canais": [f"whatsapp:{N}"], "escuta_aprovada": "true"}),))
    assert estado_remetente(con, N) == ("pendente", None)
    assert estado_remetente(con, "+5511900000000") == ("pendente", None)


def test_aprovar_exige_papel_valido(con):
    with pytest.raises(ValueError):
        aprovar(con, N, "chefe", "Fulano", "ricardo")
    assert con.execute("select count(*) from pessoa").fetchone()[0] == 0


def test_aprovar_cria_pessoa_e_vira_aprovado(con):
    registrar_remetente_visto(con, N, AGORA)
    pid = aprovar(con, N, "familia", "Fulano", "ricardo")
    assert estado_remetente(con, N) == ("aprovado", pid)
    d = json.loads(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()[0])
    assert d["escuta_aprovada"] is True and d["papel_escuta"] == "familia" and f"whatsapp:{N}" in d["canais"]
    assert pid == aprovar(con, N, "prestador", None, "ricardo")  # atualiza, não duplica
    assert con.execute("select count(*) from pessoa").fetchone()[0] == 1
    assert con.execute("select count(*) from decisao").fetchone()[0] == 2
    assert fila(con) == []


def test_aprovar_pessoa_existente_com_canal_preserva_dados(con):
    con.execute("insert into pessoa(id, nome, dados) values ('p1','Fulano', ?)", (json.dumps({"canais": [f"whatsapp:{N}"], "pode_pedir": True}),))
    assert aprovar(con, N, "cobranca", None, "ricardo") == "p1"
    d = json.loads(con.execute("select dados from pessoa where id='p1'").fetchone()[0])
    assert d["pode_pedir"] is True and d["canais"] == [f"whatsapp:{N}"]


def test_fila_traz_nome_do_contato(con):
    registrar_remetente_visto(con, N, AGORA)
    registrar_remetente_visto(con, N, AGORA)
    con.execute("insert into contato_google(conta, telefone, nome) values ('c', ?, 'Maria')", (N,))
    assert fila(con) == [{"numero": N, "nome": "Maria", "qtd": 2}]


def test_ignorar_apaga_texto_das_mensagens_retidas(con):
    registrar_remetente_visto(con, N, AGORA)
    _msg(con)
    ignorar(con, N, "ricardo")
    assert estado_remetente(con, N) == ("ignorado", None)
    r = con.execute("select texto, anexo_caminho from escuta_msg").fetchone()
    assert r[0] is None and r[1] is None


def test_bloquear_apaga_e_nao_volta_pendente(con):
    registrar_remetente_visto(con, N, AGORA)
    _msg(con)
    bloquear(con, N, "ricardo")
    registrar_remetente_visto(con, N, AGORA)
    assert estado_remetente(con, N) == ("bloqueado", None)
    r = con.execute("select texto, anexo_caminho from escuta_msg").fetchone()
    assert r[0] is None and r[1] is None
    assert fila(con) == []


def test_aviso_novo_remetente_uma_vez_e_sem_texto(con):
    registrar_remetente_visto(con, N, AGORA)
    _msg(con, texto="minha senha ZZSEGREDO")
    avisar_novo(con, N, AGORA)
    avisar_novo(con, N, AGORA)
    linhas = con.execute("select tipo, payload from aviso").fetchall()
    assert len(linhas) == 1 and linhas[0][0] == "escuta_novo_remetente"
    assert json.loads(linhas[0][1]) == {"numero": N, "nome": None}
    assert "ZZSEGREDO" not in linhas[0][1]
