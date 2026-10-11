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


def _pessoa(con, pid, dados, excl=None):
    con.execute("insert into pessoa(id, nome, dados, excluido_em) values (?,?,?,?)", (pid, pid, json.dumps(dados), excl))


def test_ignorar_so_apaga_arquivo_dentro_do_spool(con, tmp_path):
    spool = tmp_path / "spool"
    (spool / "anexos").mkdir(parents=True)
    dentro, fora = spool / "anexos" / "a.bin", tmp_path / "fora.bin"
    dentro.write_text("x")
    fora.write_text("x")
    registrar_remetente_visto(con, N, AGORA)
    _msg(con, anexo=str(dentro))
    _msg(con, anexo=str(fora))
    _msg(con, anexo=str(spool / ".." / "fora.bin"))
    ignorar(con, N, "ricardo", spool=spool)
    assert not dentro.exists() and fora.exists()
    assert con.execute("select count(*) from escuta_msg where anexo_caminho is not null").fetchone()[0] == 0


def test_sem_spool_nao_apaga_arquivo(con, tmp_path):
    f = tmp_path / "a.bin"
    f.write_text("x")
    registrar_remetente_visto(con, N, AGORA)
    _msg(con, anexo=str(f))
    bloquear(con, N, "ricardo")
    assert f.exists()
    assert con.execute("select anexo_caminho from escuta_msg").fetchone()[0] is None


def test_reaprovar_depois_de_bloquear(con):
    registrar_remetente_visto(con, N, AGORA)
    bloquear(con, N, "ricardo")
    pid = aprovar(con, N, "familia", "Fulano", "ricardo")
    assert estado_remetente(con, N) == ("aprovado", pid)


def test_ignorar_nao_rebaixa_bloqueado(con):
    registrar_remetente_visto(con, N, AGORA)
    bloquear(con, N, "ricardo")
    ignorar(con, N, "ricardo")
    assert estado_remetente(con, N) == ("bloqueado", None)


def test_bloquear_e_ignorar_desaprovam_a_pessoa(con):
    for acao in (bloquear, ignorar):
        con.execute("delete from pessoa")
        pid = aprovar(con, N, "familia", "Fulano", "ricardo")
        con.execute("update escuta_remetente set estado='aprovado' where numero=?", (N,))
        acao(con, N, "ricardo")
        assert json.loads(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()[0])["escuta_aprovada"] is False
        assert estado_remetente(con, N)[0] != "aprovado"


def test_aprovado_sem_pessoa_aprovada_volta_para_a_fila(con):
    registrar_remetente_visto(con, N, AGORA)
    pid = aprovar(con, N, "familia", "Fulano", "ricardo")
    assert fila(con) == []
    con.execute("update pessoa set excluido_em='2026-10-11' where id=?", (pid,))
    assert estado_remetente(con, N) == ("pendente", None)
    assert [f["numero"] for f in fila(con)] == [N]


def test_telefone_em_outros_formatos_casa(con):
    _pessoa(con, "p1", {"canais": ["whatsapp:55 (11) 91234-5678"], "escuta_aprovada": True, "papel_escuta": "familia"})
    assert estado_remetente(con, N) == ("aprovado", "p1")
    _pessoa(con, "p0", {"canais": ["whatsapp:5511912345678"]})
    assert estado_remetente(con, N) == ("aprovado", "p1")  # a aprovada vence
    assert aprovar(con, N, "prestador", None, "r") == "p1"
    assert con.execute("select count(*) from pessoa where id like 'wa-%'").fetchone()[0] == 0


def test_entradas_invalidas_nao_aprovam(con):
    _pessoa(con, "a", {"canais": f"whatsapp:{N}", "escuta_aprovada": True, "papel_escuta": "familia"})
    _pessoa(con, "b", {"canais": [f"whatsapp:{N}"], "escuta_aprovada": True, "papel_escuta": "chefe"})
    _pessoa(con, "c", {"canais": [f"whatsapp:{N}"], "escuta_aprovada": 1, "papel_escuta": "familia"})
    _pessoa(con, "d", {"canais": [f"whatsapp:{N}"], "escuta_aprovada": True, "papel_escuta": "familia"}, excl="2026-01-01")
    assert estado_remetente(con, N) == ("pendente", None)


def test_aprovar_reativa_pessoa_excluida(con):
    pid = aprovar(con, N, "familia", "Fulano", "r")
    con.execute("update pessoa set excluido_em='2026-10-11' where id=?", (pid,))
    assert aprovar(con, N, "familia", "Fulano", "r") == pid
    assert estado_remetente(con, N) == ("aprovado", pid)


def test_ignorar_apaga_texto_de_crise_mas_nao_de_outras_processadas(con):
    registrar_remetente_visto(con, N, AGORA)
    _msg(con, texto="crise-texto")
    _msg(con, texto="pedido-texto")
    con.execute("update escuta_msg set estado='processada', tipo='crise' where texto='crise-texto'")
    con.execute("update escuta_msg set estado='processada', tipo='pedido' where texto='pedido-texto'")
    ignorar(con, N, "ricardo")
    assert [r[0] for r in con.execute("select texto from escuta_msg where tipo='crise'")] == [None]
    assert [r[0] for r in con.execute("select texto from escuta_msg where tipo='pedido'")] == ["pedido-texto"]


def test_descartar_com_anexos_trocado_por_symlink_nao_apaga_a_vitima(con, tmp_path, monkeypatch):
    import os
    from gabi.escuta import spool_seguro
    spool = tmp_path / "spool"
    (spool / "anexos").mkdir(parents=True)
    vitima = tmp_path / "dados-do-brain"
    vitima.mkdir()
    (vitima / "a.bin").write_text("SEGREDO")
    (spool / "anexos" / "a.bin").write_text("x")

    def troca():
        os.rename(spool / "anexos", spool / "anexos-orig")
        (spool / "anexos").symlink_to(vitima, target_is_directory=True)
    monkeypatch.setattr(spool_seguro, "_gancho", troca)
    registrar_remetente_visto(con, N, AGORA)
    _msg(con, anexo=str(spool / "anexos" / "a.bin"))
    ignorar(con, N, "ricardo", spool=spool)
    assert (vitima / "a.bin").read_text() == "SEGREDO"


def test_i4_id_cru_aprovado_casa_pelo_canal_exato(con):
    lid = "123456789012345@lid"
    pid = aprovar(con, lid, "familia", "Tia", "teste")
    d = json.loads(con.execute("select dados from pessoa where id=?", (pid,)).fetchone()[0])
    assert f"whatsapp:{lid}" in d["canais"]
    assert estado_remetente(con, lid) == ("aprovado", pid)
