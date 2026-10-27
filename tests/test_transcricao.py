"""Transcrição local de áudio (ADR-034), opcional: sem o pacote ou desligada, tudo segue e o áudio fica guardado sem texto. Consome: gabi.transcricao, gabi.anexos."""
import sys
import types
from pathlib import Path

import pytest

from gabi import anexos, transcricao
from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent / "migrations"


class _Seg:
    def __init__(self, texto):
        self.text = texto


def _falso(monkeypatch, segmentos=(" oi ", " tudo bem ")):
    chamadas = {"init": [], "transcribe": []}

    class WhisperModel:
        def __init__(self, *a, **kw):
            chamadas["init"].append((a, kw))

        def transcribe(self, caminho, **kw):
            chamadas["transcribe"].append((caminho, kw))
            return iter([_Seg(t) for t in segmentos]), object()

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return chamadas


@pytest.fixture(autouse=True)
def _limpo(monkeypatch, tmp_path):
    monkeypatch.delenv("TRANSCRICAO", raising=False)
    monkeypatch.setattr(transcricao, "ARQUIVO_ENV", tmp_path / "sem-arquivo.env")


def test_carregar_sem_pacote_devolve_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import falha
    assert transcricao.carregar() is None


def test_carregar_desligada_por_variavel_devolve_none(monkeypatch, tmp_path):
    _falso(monkeypatch)
    monkeypatch.setenv("TRANSCRICAO", "desligada")
    assert transcricao.carregar() is None
    monkeypatch.delenv("TRANSCRICAO")
    arq = tmp_path / "transcricao.env"
    arq.write_text("# desligar\nTRANSCRICAO=desligada\n")
    monkeypatch.setattr(transcricao, "ARQUIVO_ENV", arq)
    assert transcricao.carregar() is None
    assert transcricao.carregar() is None
    arq.write_text("TRANSCRICAO=ligada\n")
    assert callable(transcricao.carregar())


def test_transcritor_usa_pt_cpu_int8(monkeypatch, tmp_path):
    ch = _falso(monkeypatch)
    t = transcricao.carregar()
    assert ch["init"] == []  # o modelo só carrega quando houver áudio
    assert t(tmp_path / "a.ogg") == "oi tudo bem"
    assert t(tmp_path / "b.ogg") == "oi tudo bem"
    (args, kw), = ch["init"]  # uma vez só por processo
    assert args == ("small",) and kw == {"device": "cpu", "compute_type": "int8", "download_root": "/var/lib/gabi-brain/modelos"}
    assert ch["transcribe"][0][0] == str(tmp_path / "a.ogg") and ch["transcribe"][0][1]["language"] == "pt"


def test_texto_vazio_vira_none(monkeypatch, tmp_path):
    _falso(monkeypatch, segmentos=("  ", ""))
    assert transcricao.carregar()(tmp_path / "a.ogg") is None


def test_retranscrever_preenche_so_audios_sem_texto(monkeypatch, tmp_path):
    con = conectar(tmp_path / "t.db")
    migrar(con, MIGR)
    destino = tmp_path / "anexos"
    (destino / "aa").mkdir(parents=True)
    for nome in ("aaa.ogg", "bbb.ogg", "ccc.jpg"):
        (destino / "aa" / nome).write_bytes(b"x")
    con.executemany("insert into anexo(tipo, arquivo, sha256, transcricao, recebido_em) values (?,?,?,?,'2026-10-27T12:00:00+00:00')",
                    [("audio", "aa/aaa.ogg", "aaa", None), ("audio", "aa/bbb.ogg", "bbb", "já tinha"), ("imagem", "aa/ccc.jpg", "ccc", None)])
    visto = []

    def transcrever(caminho):
        visto.append(caminho.name)
        return "texto novo" if caminho.name == "aaa.ogg" else None

    assert anexos.retranscrever(con, transcrever, destino) == 1
    assert visto == ["aaa.ogg"]
    assert {r["sha256"]: r["transcricao"] for r in con.execute("select * from anexo")} == {"aaa": "texto novo", "bbb": "já tinha", "ccc": None}
