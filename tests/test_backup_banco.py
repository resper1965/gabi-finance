import stat
from datetime import date
from pathlib import Path

import pytest

from gabi.backup import backup_db, main, testar_restauracao
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent / "migrations"
HOJE = date(2026, 10, 8)


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    con = conectar(p)
    migrar(con, MIGRACOES)
    for i in range(5):
        con.execute("insert into pessoa(id, nome) values (?, ?)", (f"p{i}", f"Pessoa {i} Açaí"))
    con.close()
    return p


def test_backup_com_banco_aberto_por_outro_processo_e_consistente(banco, tmp_path):
    escritor = conectar(banco)
    escritor.execute("pragma wal_autocheckpoint=0")
    escritor.execute("insert into pessoa(id, nome) values ('novo', 'Entrou no WAL')")  # só no WAL
    leitor = conectar(banco)
    destino = backup_db(leitor, tmp_path / "bk", HOJE)
    r = testar_restauracao(destino, ["pessoa"])
    assert r == {"ok": True, "contagens": {"pessoa": 6}}


def test_backup_nome_permissao_e_diretorio(banco, tmp_path):
    destino = backup_db(conectar(banco), tmp_path / "bk", HOJE)
    assert destino.name == "gabi-brain-2026-10-08.sqlite"
    assert stat.S_IMODE(destino.stat().st_mode) == 0o600
    assert stat.S_IMODE(destino.parent.stat().st_mode) == 0o700


def test_backup_nao_sobrescreve_dia(banco, tmp_path):
    con = conectar(banco)
    backup_db(con, tmp_path / "bk", HOJE)
    with pytest.raises(FileExistsError):
        backup_db(con, tmp_path / "bk", HOJE)


def test_backup_nao_deixa_wal_nem_parcial(banco, tmp_path):
    backup_db(conectar(banco), tmp_path / "bk", HOJE)
    restos = [p.name for p in (tmp_path / "bk").iterdir() if not p.name.endswith(".sqlite")]
    assert restos == []


def test_testar_restauracao_ok_contagens_iguais_as_da_origem(banco, tmp_path):
    destino = backup_db(conectar(banco), tmp_path / "bk", HOJE)
    r = testar_restauracao(destino, ["pessoa", "acesso"])
    assert r == {"ok": True, "contagens": {"pessoa": 5, "acesso": 0}}


def test_arquivo_corrompido_falha_na_restauracao(banco, tmp_path):
    destino = backup_db(conectar(banco), tmp_path / "bk", HOJE)
    dados = bytearray(destino.read_bytes())
    dados[4096:] = b"\xff" * (len(dados) - 4096)  # tudo depois da 1ª página: corrompe com certeza, qualquer que seja o tamanho do banco
    destino.write_bytes(bytes(dados))
    r = testar_restauracao(destino, ["pessoa"])
    assert r["ok"] is False


def test_arquivo_que_nao_e_sqlite_falha_sem_excecao(tmp_path):
    lixo = tmp_path / "lixo.sqlite"
    lixo.write_bytes(b"isto nao e um banco" * 100)
    assert testar_restauracao(lixo, ["pessoa"])["ok"] is False


def test_testar_restauracao_nao_altera_o_backup(banco, tmp_path):
    destino = backup_db(conectar(banco), tmp_path / "bk", HOJE)
    antes = destino.read_bytes()
    testar_restauracao(destino, ["pessoa"])
    assert destino.read_bytes() == antes
    assert not list(destino.parent.glob("*-wal")) and not list(destino.parent.glob("*-shm"))


def test_main_registra_rodada_backup_e_testa(banco, tmp_path):
    assert main(banco, tmp_path / "bk", hoje=HOJE, testar=True) == 0
    r = conectar(banco).execute("select fonte, status from rodada where fonte='backup'").fetchone()
    assert (r["fonte"], r["status"]) == ("backup", "ok")


def test_main_com_backup_corrompido_retorna_erro_e_rodada_erro(banco, tmp_path, monkeypatch):
    import gabi.backup as b
    monkeypatch.setattr(b, "testar_restauracao", lambda *a, **k: {"ok": False, "contagens": {}})
    assert main(banco, tmp_path / "bk", hoje=HOJE, testar=True) == 1
    assert conectar(banco).execute("select status from rodada where fonte='backup'").fetchone()["status"] == "erro"


def test_main_reexecucao_no_mesmo_dia_nao_e_falha(banco, tmp_path, capsys):
    from gabi.backup import main
    assert main(banco, tmp_path / "bk", HOJE) == 0
    assert main(banco, tmp_path / "bk", HOJE) == 0
    assert "já existe" in capsys.readouterr().out
