import json
import shutil
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.caixa import ingerir_spool, normalizar_telefone, registrar_remetente_visto

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-11T10:00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _msg(pasta, nome, **kw):
    pasta.mkdir(parents=True, exist_ok=True)
    d = {"id_externo": nome, "de": "5511912345678@s.whatsapp.net", "grupo": False, "id_grupo": None,
         "recebida_em": "2026-10-11T09:00:00", "texto": "oi", "anexo": None}
    d.update(kw)
    (pasta / f"{nome}.json").write_text(json.dumps(d))


def test_telefone_formatos_equivalentes():
    for bruto in ("5511912345678@s.whatsapp.net", "+55 11 91234-5678", "11912345678"):
        assert normalizar_telefone(bruto) == "+5511912345678"


def test_telefone_invalido_none():
    for bruto in ("", "abc", "123", "551191234567890123"):
        assert normalizar_telefone(bruto) is None


def test_ingerir_grava_uma_vez(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "a1")
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert not (pasta / "a1.json").exists() and (pasta / "lidos" / "a1.json").exists()
    shutil.copy(pasta / "lidos" / "a1.json", pasta / "a1.json")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 1
    assert con.execute("select estado from escuta_msg").fetchone()[0] == "nova"
    assert con.execute("select qtd from escuta_remetente").fetchone()[0] == 1


def test_grupo_marcado(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "g1", grupo=True, id_grupo="123@g.us")
    ingerir_spool(con, pasta, AGORA)
    r = con.execute("select grupo, id_grupo from escuta_msg").fetchone()
    assert (r["grupo"], r["id_grupo"]) == (1, "123@g.us")
    assert con.execute("select count(*) from escuta_remetente").fetchone()[0] == 0


def test_bloqueado_nao_e_gravado(con, tmp_path):
    con.execute("insert into escuta_remetente(numero, estado, qtd) values ('+5511912345678','bloqueado',0)")
    pasta = tmp_path / "spool"
    _msg(pasta, "b1")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0
    assert (pasta / "lidos" / "b1.json").exists()


def test_desconhecido_gravado_e_vira_pendente(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "u1")
    assert ingerir_spool(con, pasta, AGORA) == 1
    r = con.execute("select estado, qtd from escuta_remetente where numero='+5511912345678'").fetchone()
    assert (r["estado"], r["qtd"]) == ("pendente", 1)


def test_malformado_vai_para_invalidos(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "ok")
    (pasta / "a-ruim.json").write_text("{nao e json")
    _msg(pasta, "sem-campos")
    (pasta / "sem-campos.json").write_text(json.dumps({"id_externo": "x"}))
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert (pasta / "invalidos" / "a-ruim.json").exists()
    assert (pasta / "invalidos" / "sem-campos.json").exists()


def test_anexo_caminho(con, tmp_path):
    pasta = tmp_path / "spool"
    _msg(pasta, "x1", anexo="foto.jpg")
    ingerir_spool(con, pasta, AGORA)
    assert con.execute("select anexo_caminho from escuta_msg").fetchone()[0] == str(pasta / "anexos" / "foto.jpg")


def test_visto_incrementa_e_nao_reabre_ignorado(con):
    registrar_remetente_visto(con, "+5511900000001", AGORA)
    registrar_remetente_visto(con, "+5511900000001", AGORA)
    r = con.execute("select estado, qtd from escuta_remetente").fetchone()
    assert (r["estado"], r["qtd"]) == ("pendente", 2)
    con.execute("update escuta_remetente set estado='ignorado'")
    registrar_remetente_visto(con, "+5511900000001", "2026-10-12T10:00:00")
    r = con.execute("select estado, qtd, vista_em from escuta_remetente").fetchone()
    assert (r["estado"], r["qtd"], r["vista_em"]) == ("ignorado", 3, "2026-10-12T10:00:00")


@pytest.mark.parametrize("anexo", ["../../x", "/etc/passwd", "a/b.jpg", "..", ".", "", "a\\b.jpg"])
def test_anexo_traversal_vai_para_invalidos(con, tmp_path, anexo):
    pasta = tmp_path / "spool"
    _msg(pasta, "t1", anexo=anexo)
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert (pasta / "invalidos" / "t1.json").exists()
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0


@pytest.mark.parametrize("campo,valor", [("anexo", 5), ("anexo", ["a"]), ("texto", ["x"]), ("texto", {"a": 1}), ("id_grupo", ["g"])])
def test_tipo_errado_invalido_e_rodada_continua(con, tmp_path, campo, valor):
    pasta = tmp_path / "spool"
    _msg(pasta, "a-ruim", **{campo: valor})
    _msg(pasta, "b-ok")
    assert ingerir_spool(con, pasta, AGORA) == 1
    assert (pasta / "invalidos" / "a-ruim.json").exists()
    assert con.execute("select id_externo from escuta_msg").fetchone()[0] == "b-ok"


def test_bloqueado_vale_para_forma_whatsapp(con, tmp_path):
    con.execute("insert into escuta_remetente(numero, estado, qtd) values ('+5511912345678','bloqueado',0)")
    pasta = tmp_path / "spool"
    _msg(pasta, "w1", de="5511912345678@s.whatsapp.net")
    assert ingerir_spool(con, pasta, AGORA) == 0
    assert con.execute("select count(*) from escuta_msg").fetchone()[0] == 0
