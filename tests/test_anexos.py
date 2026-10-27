"""Anexos (ADR-034): coleta do cache do Hermes para o disco do brain, caixa de entrada e ligação ao projeto. Consome: gabi.anexos, gabi.projetos. AGORA = 27/10/2026 12:00 BRT."""
import datetime as dt
import os
import stat
from pathlib import Path

import pytest

from gabi import anexos, projetos
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


@pytest.fixture
def dirs(tmp_path):
    o, d = tmp_path / "cache", tmp_path / "anexos"
    o.mkdir()
    return o, d


def _arq(pasta, nome, conteudo=b"x", idade_s=3600):
    f = pasta / nome
    f.write_bytes(conteudo)
    t = AGORA.timestamp() - idade_s
    os.utime(f, (t, t))
    return f


def _coletar(con, dirs, **kw):
    return anexos.coletar(con, AGORA, [dirs[0]], dirs[1], **kw)


def test_coleta_imagem_e_audio_e_classifica_pelo_tipo(con, dirs):
    _arq(dirs[0], "a.JPG", b"foto")
    _arq(dirs[0], "b.ogg", b"voz")
    _arq(dirs[0], "c.png", b"print")
    r = _coletar(con, dirs)
    assert r == {"novos": 3, "repetidos": 0, "ignorados": 0, "adiados": 0}
    tipos = {row["tipo"] for row in con.execute("select tipo from anexo")}
    assert tipos == {"imagem", "audio"}
    row = con.execute("select * from anexo where tipo='audio'").fetchone()
    assert (dirs[1] / row["arquivo"]).read_bytes() == b"voz" and row["arquivo"].endswith(".ogg") and row["arquivo"].startswith(row["sha256"][:2] + "/")
    assert row["recebido_em"] == (AGORA - dt.timedelta(hours=1)).isoformat() and row["projeto_id"] is None
    assert (dirs[0] / "b.ogg").exists()  # copia, não move


def test_mesmo_arquivo_duas_vezes_gera_um_anexo(con, dirs):
    _arq(dirs[0], "whats.jpg", b"igual")
    _arq(dirs[0], "telegram.jpeg", b"igual")
    assert _coletar(con, dirs) == {"novos": 1, "repetidos": 1, "ignorados": 0, "adiados": 0}
    assert _coletar(con, dirs)["repetidos"] == 2
    assert con.execute("select count(*) from anexo").fetchone()[0] == 1


def test_arquivo_recente_espera_a_proxima_rodada(con, dirs):
    _arq(dirs[0], "gravando.jpg", b"meio", idade_s=5)
    assert _coletar(con, dirs) == {"novos": 0, "repetidos": 0, "ignorados": 0, "adiados": 1}
    assert con.execute("select count(*) from anexo").fetchone()[0] == 0
    _arq(dirs[0], "gravando.jpg", b"completo", idade_s=60)
    assert _coletar(con, dirs)["novos"] == 1


def test_arquivo_gigante_e_ignorado(con, dirs):
    _arq(dirs[0], "enorme.jpg", b"0123456789")
    assert _coletar(con, dirs, limite_bytes=5) == {"novos": 0, "repetidos": 0, "ignorados": 1, "adiados": 0}
    assert _coletar(con, dirs)["novos"] == 1  # o limite padrão é 50 MB
    assert anexos.LIMITE_BYTES == 50 * 1024 * 1024


def test_extensao_desconhecida_e_ignorada(con, dirs):
    _arq(dirs[0], "doc.pdf")
    _arq(dirs[0], "semextensao")
    (dirs[0] / "pasta.jpg").mkdir()
    assert _coletar(con, dirs) == {"novos": 0, "repetidos": 0, "ignorados": 2, "adiados": 0}


def test_permissoes_0700_e_0600(con, dirs):
    _arq(dirs[0], "a.jpg", b"foto")
    _coletar(con, dirs)
    arq = dirs[1] / con.execute("select arquivo from anexo").fetchone()[0]
    assert stat.S_IMODE(arq.stat().st_mode) == 0o600
    assert stat.S_IMODE(arq.parent.stat().st_mode) == 0o700 and stat.S_IMODE(dirs[1].stat().st_mode) == 0o700


def test_origem_inexistente_nao_quebra(con, dirs, tmp_path):
    r = anexos.coletar(con, AGORA, [tmp_path / "nao-existe"], dirs[1])
    assert r == {"novos": 0, "repetidos": 0, "ignorados": 0, "adiados": 0}


def test_transcricao_gravada_e_excecao_vira_none(con, dirs):
    _arq(dirs[0], "bom.ogg", b"bom")
    _arq(dirs[0], "ruim.ogg", b"ruim")
    _arq(dirs[0], "foto.jpg", b"foto")
    chamados = []

    def transcrever(caminho):
        chamados.append(caminho.suffix)
        if caminho.read_bytes() == b"ruim":
            raise RuntimeError("falhou")
        return "oi, o carro fica pronto dia 20"

    assert _coletar(con, dirs, transcrever=transcrever)["novos"] == 3
    t = {r["sha256"]: r["transcricao"] for r in con.execute("select * from anexo")}
    assert sorted(v for v in t.values() if v) == ["oi, o carro fica pronto dia 20"] and sum(v is None for v in t.values()) == 2
    assert chamados == [".ogg", ".ogg"]  # só áudio


def test_log_do_main_so_tem_contagens(con, dirs, tmp_path, monkeypatch, capsys):
    _arq(dirs[0], "segredo-do-joao.jpg", b"foto")
    monkeypatch.setenv("ANEXOS_ORIGENS", str(dirs[0]))
    monkeypatch.setenv("ANEXOS_DIR", str(dirs[1]))
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "t.db"))
    monkeypatch.setattr(anexos, "_agora", lambda: AGORA)
    assert anexos.main([]) == 0
    saida = capsys.readouterr().out
    assert saida.strip() == "anexos: novos=1 repetidos=0 ignorados=0 adiados=0" and "joao" not in saida


def _anexo(con, tipo="imagem", sha="a", dias=1, projeto_id=None, transcricao=None):
    return con.execute("insert into anexo(tipo, arquivo, sha256, transcricao, recebido_em, projeto_id) values (?,?,?,?,?,?)",
                       (tipo, f"{sha}.x", sha, transcricao, (AGORA - dt.timedelta(days=dias)).isoformat(), projeto_id)).lastrowid


def test_anexos_recentes_so_os_sem_projeto_e_dentro_de_14_dias(con):
    p = projetos.criar(con, AGORA, "hermes", "hermes", "Carro")["id"]
    novo = _anexo(con, "audio", "n", dias=1, transcricao="oi")
    _anexo(con, "imagem", "v", dias=20)
    _anexo(con, "imagem", "l", dias=2, projeto_id=p)
    r = projetos.anexos_recentes(con, AGORA)
    assert r == [{"id": novo, "tipo": "audio", "recebido_em": (AGORA - dt.timedelta(days=1)).isoformat(), "transcricao": "oi"}]
    assert len(projetos.anexos_recentes(con, AGORA, dias=30)) == 2


def test_anexar_liga_e_recusa_anexo_inexistente_ou_ja_ligado_a_outro_projeto(con):
    a = projetos.criar(con, AGORA, "hermes", "hermes", "A")["id"]
    b = projetos.criar(con, AGORA, "hermes", "hermes", "B")["id"]
    x = _anexo(con)
    assert projetos.anexar(con, AGORA, "hermes", "hermes", a, anexo_id=x)["projeto_id"] == a
    assert projetos.anexar(con, AGORA, "hermes", "hermes", a, anexo_id=x)["projeto_id"] == a  # repetir é inofensivo
    with pytest.raises(ValueError):
        projetos.anexar(con, AGORA, "hermes", "hermes", b, anexo_id=x)
    with pytest.raises(ValueError):
        projetos.anexar(con, AGORA, "hermes", "hermes", a, anexo_id=999)
    with pytest.raises(ValueError):
        projetos.anexar(con, AGORA, "hermes", "hermes", a)
    with pytest.raises(ValueError):
        projetos.anexar(con, AGORA, "hermes", "hermes", a, anexo_id=x, paperless_id=7)
    with pytest.raises(LookupError):
        projetos.anexar(con, AGORA, "hermes", "hermes", 999, anexo_id=x)
    assert projetos.anexos_recentes(con, AGORA) == []


def test_anexar_documento_do_paperless(con):
    p = projetos.criar(con, AGORA, "hermes", "hermes", "Carro")["id"]
    d = projetos.anexar(con, AGORA, "hermes", "hermes", p, paperless_id=321)
    assert d["tipo"] == "documento" and d["paperless_id"] == 321 and d["projeto_id"] == p
    assert projetos.anexar(con, AGORA, "hermes", "hermes", p, paperless_id=321)["id"] == d["id"]
    assert projetos.ver(con, AGORA, p)["anexos"] == 1
    assert projetos.anexos_recentes(con, AGORA) == []
