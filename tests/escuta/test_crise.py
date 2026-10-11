import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.crise import palavras_risco, tem_risco

MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def test_tem_risco_sem_acento_e_caixa():
    assert tem_risco("Não aguento MAIS, quero me MATAR", ["matar"])
    assert tem_risco("preciso de ajuda urgente", ["URGÊNCIA", "Ajuda"])
    assert not tem_risco("tudo bem", ["matar"])


def test_palavra_inteira_nao_casa_pedaco():
    assert not tem_risco("vou tomar um amatar", ["matar"])
    assert not tem_risco("socorrista chegou", ["socorro"])
    assert tem_risco("socorro!", ["socorro"])


def test_multi_palavra():
    assert tem_risco("eu vou  me matar hoje", ["me matar"])
    assert not tem_risco("eu vou me matarei", ["me matar"])


def test_lista_sem_entradas_vazias():
    assert not tem_risco("qualquer coisa", ["", "  "])


def test_sem_parametro_lista_vazia(con):
    assert palavras_risco(con) == []


def test_parametro_lido_do_banco(con):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (json.dumps(["socorro", "me matar"]),))
    assert palavras_risco(con) == ["socorro", "me matar"]


@pytest.mark.parametrize("valor", ["", "não é json", '{"a":1}', '"x"'])
def test_parametro_invalido_lista_vazia(con, valor):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (valor,))
    assert palavras_risco(con) == []


def test_parametro_ignora_itens_nao_texto(con):
    con.execute("insert into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (json.dumps(["socorro", 3, None]),))
    assert palavras_risco(con) == ["socorro"]


# ---------------- palavras-risco.json para o ouvinte ----------------
def _define(con, lista):
    con.execute("insert or replace into parametro(chave, valor) values ('escuta.palavras_risco', ?)", (json.dumps(lista),))


def test_escrever_palavras_risco_grava_lista_atomica_0640(con, tmp_path):
    import stat
    from gabi.escuta.crise import escrever_palavras_risco
    _define(con, ["matar", "sem saída"])
    spool = tmp_path / "spool"
    spool.mkdir()
    assert escrever_palavras_risco(con, spool) is True
    alvo = spool / "palavras-risco.json"
    assert json.loads(alvo.read_text(encoding="utf-8")) == ["matar", "sem saída"]
    assert stat.S_IMODE(alvo.stat().st_mode) == 0o640
    assert not (spool / "palavras-risco.json.tmp").exists()


def test_escrever_palavras_risco_igual_nao_reescreve(con, tmp_path):
    import os
    from gabi.escuta.crise import escrever_palavras_risco
    _define(con, ["matar"])
    escrever_palavras_risco(con, tmp_path)
    alvo = tmp_path / "palavras-risco.json"
    os.utime(alvo, (1000, 1000))
    assert escrever_palavras_risco(con, tmp_path) is False
    assert alvo.stat().st_mtime == 1000
    _define(con, ["matar", "suicídio"])
    assert escrever_palavras_risco(con, tmp_path) is True
    assert json.loads(alvo.read_text(encoding="utf-8")) == ["matar", "suicídio"]


def test_ingestao_nao_trata_palavras_risco_como_mensagem(con, tmp_path):
    from gabi.escuta.caixa import ingerir_spool
    from gabi.escuta.crise import escrever_palavras_risco
    _define(con, ["matar"])
    escrever_palavras_risco(con, tmp_path)
    ingerir_spool(con, tmp_path, "2026-10-11T10:00:00")
    assert (tmp_path / "palavras-risco.json").exists() and not (tmp_path / "invalidos").exists()


# ---------------- listener comprometido: symlink plantado no spool ----------------
def test_symlink_plantado_no_tmp_previsivel_e_recusado_pelo_o_excl(con, tmp_path, monkeypatch):
    import os
    import secrets
    from gabi.escuta import crise
    vitima = tmp_path / "gabi.db"
    vitima.write_bytes(b"BANCO-INTACTO")
    os.chmod(vitima, 0o600)
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(secrets, "token_hex", lambda n=8: "previsivel")
    (spool / f"palavras-risco.json.{os.getpid()}.previsivel.tmp").symlink_to(vitima)  # o ouvinte adivinhou o nome
    _define(con, ["matar"])
    with pytest.raises(OSError):  # O_EXCL|O_NOFOLLOW recusa; a rodada engole como palavras_erro
        crise.escrever_palavras_risco(con, spool)
    assert vitima.read_bytes() == b"BANCO-INTACTO" and (vitima.stat().st_mode & 0o777) == 0o600
    assert not (spool / "palavras-risco.json").exists()


def test_tmp_aleatorio_nao_colide_e_grava(con, tmp_path):
    from gabi.escuta.crise import escrever_palavras_risco
    spool = tmp_path / "spool"
    spool.mkdir()
    _define(con, ["matar"])
    assert escrever_palavras_risco(con, spool) is True
    assert json.loads((spool / "palavras-risco.json").read_text(encoding="utf-8")) == ["matar"]


def test_symlink_no_proprio_alvo_e_substituido_sem_tocar_na_vitima(con, tmp_path):
    from gabi.escuta.crise import escrever_palavras_risco
    vitima = tmp_path / "gabi.db"
    vitima.write_bytes(b"BANCO-INTACTO")
    (tmp_path / "palavras-risco.json").symlink_to(vitima)
    _define(con, ["matar"])
    escrever_palavras_risco(con, tmp_path)
    assert vitima.read_bytes() == b"BANCO-INTACTO"
    assert not (tmp_path / "palavras-risco.json").is_symlink()


def test_fifo_no_alvo_nao_trava_a_rodada(con, tmp_path):
    import os
    import signal
    from gabi.escuta.crise import escrever_palavras_risco
    os.mkfifo(tmp_path / "palavras-risco.json")
    _define(con, ["matar"])
    signal.alarm(5)
    try:
        assert escrever_palavras_risco(con, tmp_path) is True
    finally:
        signal.alarm(0)
    assert json.loads((tmp_path / "palavras-risco.json").read_text(encoding="utf-8")) == ["matar"]


def test_falha_na_escrita_limpa_o_tmp(con, tmp_path, monkeypatch):
    import os
    from gabi.escuta import crise
    _define(con, ["matar"])
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("falha")))
    spool = tmp_path / "spool"
    spool.mkdir()
    with pytest.raises(OSError):
        crise.escrever_palavras_risco(con, spool)
    assert list(spool.iterdir()) == []
