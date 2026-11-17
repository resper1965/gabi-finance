import datetime as dt
import shutil
import subprocess
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.exportacao import exportar

pytestmark = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg não instalado")
MIGR = Path(__file__).parent.parent / "migrations"
HOJE = dt.date(2026, 10, 18)


@pytest.fixture
def chaves(tmp_path):
    """Par de chaves de teste num homedir descartável; devolve (arquivo da pública, homedir com a privada)."""
    home = tmp_path / "gnupg"; home.mkdir(mode=0o700)
    subprocess.run(["gpg", "--homedir", str(home), "--batch", "--passphrase", "", "--quick-generate-key", "teste@gabi.local", "default", "default", "never"],
                   check=True, capture_output=True)
    pub = tmp_path / "backup.pub"
    pub.write_bytes(subprocess.run(["gpg", "--homedir", str(home), "--armor", "--export", "teste@gabi.local"], check=True, capture_output=True).stdout)
    return pub, home


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGR)
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    return c


def _decifrar(pacote: Path, home: Path, saida: Path) -> Path:
    subprocess.run(["gpg", "--homedir", str(home), "--batch", "--pinentry-mode", "loopback", "--passphrase", "", "--output", str(saida), "--decrypt", str(pacote)], check=True, capture_output=True)
    return saida


def test_exportacao_gera_pacote_criptografado_e_registra_rodada(con, tmp_path, chaves):
    pub, home = chaves
    pacote = exportar(con, tmp_path / "exp", pub, HOJE)
    assert pacote.name == "gabi-finance-2026-10-18.sqlite.gpg" and pacote.stat().st_mode & 0o777 == 0o600
    assert b"SQLite format 3" not in pacote.read_bytes()                     # criptografado de verdade
    banco = _decifrar(pacote, home, tmp_path / "volta.sqlite")                # e restaurável com a chave privada
    assert conectar(banco).execute("select nome from pessoa").fetchone()[0] == "Ana"
    r = con.execute("select fonte, status, lidos from rodada where fonte='exportacao'").fetchone()
    assert tuple(r) == ("exportacao", "ok", 1)
    assert not list((tmp_path / "exp").glob("*.sqlite"))                      # nada em claro sobra na pasta de saída


def test_exportacao_falha_se_restauracao_falha(con, tmp_path, chaves, monkeypatch):
    pub, _ = chaves
    monkeypatch.setattr("gabi.exportacao.testar_restauracao", lambda arq, tabelas: {"ok": False, "contagens": {}})
    with pytest.raises(RuntimeError):
        exportar(con, tmp_path / "exp", pub, HOJE)
    assert con.execute("select status from rodada where fonte='exportacao'").fetchone()[0] == "erro"
    assert not list((tmp_path / "exp").glob("*"))                              # nem pacote nem rascunho em claro


def test_sem_chave_publica_nao_exporta_em_claro(con, tmp_path):
    with pytest.raises(FileNotFoundError):
        exportar(con, tmp_path / "exp", tmp_path / "nao-existe.pub", HOJE)
    assert not list((tmp_path / "exp").glob("*")) if (tmp_path / "exp").exists() else True


def test_mantem_so_os_ultimos_pacotes(con, tmp_path, chaves):
    pub, _ = chaves
    for k in range(5):
        exportar(con, tmp_path / "exp", pub, HOJE - dt.timedelta(days=7 * (4 - k)), manter=3)
    assert sorted(p.name for p in (tmp_path / "exp").glob("*.gpg")) == [f"gabi-finance-2026-10-{d}.sqlite.gpg" for d in ("04", "11", "18")]


def test_mesmo_dia_duas_vezes_nao_duplica_nem_falha(con, tmp_path, chaves):
    pub, _ = chaves
    exportar(con, tmp_path / "exp", pub, HOJE)
    assert exportar(con, tmp_path / "exp", pub, HOJE).name == "gabi-finance-2026-10-18.sqlite.gpg" and len(list((tmp_path / "exp").glob("*.gpg"))) == 1
