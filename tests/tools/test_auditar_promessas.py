import datetime as dt
import os
import sqlite3
import time

from tools import auditar_promessas as ap

T0 = dt.datetime(2026, 10, 24, 12, 0).timestamp()
ESCRITA = "mcp__gabi_brain__familia_registrar_pessoa"


def _banco(tmp_path, msgs, source="telegram"):
    """msgs: lista de (role, content, tool_name). Timestamps crescentes a partir de T0."""
    p = tmp_path / "state.db"
    con = sqlite3.connect(p)
    con.execute("create table sessions(id text primary key, source text)")
    con.execute("create table messages(id integer primary key, session_id text, role text, content text, tool_name text, timestamp real)")
    con.execute("insert into sessions values('s1', ?)", (source,))
    for i, (role, content, tool) in enumerate(msgs):
        con.execute("insert into messages(session_id, role, content, tool_name, timestamp) values('s1', ?, ?, ?, ?)",
                    (role, content, tool, T0 + i))
    con.commit()
    con.close()
    return p


DESDE = dt.datetime(2026, 10, 1)
USER = ("user", "chafic é meu irmão", None)
PROMESSA = ("assistant", "Anotado! Chafic, seu irmão.", None)


def test_promessa_sem_ferramenta_e_caso(tmp_path):
    p = _banco(tmp_path, [USER, PROMESSA])
    casos = ap.promessas_sem_escrita(p, DESDE)
    assert len(casos) == 1
    assert casos[0]["sessao"] == "s1" and casos[0]["trecho"].startswith("Anotado!")


def test_promessa_com_escrita_ok_nao_e_caso(tmp_path):
    p = _banco(tmp_path, [USER, ("tool", '{"ok": true}', ESCRITA), PROMESSA])
    assert ap.promessas_sem_escrita(p, DESDE) == []


def test_escrita_com_erro_e_caso(tmp_path):
    p = _banco(tmp_path, [USER, ("tool", '{"erro": "pessoa_ambigua"}', ESCRITA), PROMESSA])
    assert len(ap.promessas_sem_escrita(p, DESDE)) == 1


def test_leitura_nao_conta(tmp_path):
    p = _banco(tmp_path, [USER, ("tool", '{"ok": true}', "mcp__gabi_brain__familia_consultar"), PROMESSA])
    assert len(ap.promessas_sem_escrita(p, DESDE)) == 1


def test_escrita_de_turno_anterior_nao_vale(tmp_path):
    p = _banco(tmp_path, [USER, ("tool", '{"ok": true}', ESCRITA), PROMESSA, USER, PROMESSA])
    assert len(ap.promessas_sem_escrita(p, DESDE)) == 1


def test_ignora_outras_fontes_e_sem_verbo(tmp_path):
    assert ap.promessas_sem_escrita(_banco(tmp_path, [USER, PROMESSA], source="cron"), DESDE) == []
    p2 = tmp_path / "b"
    p2.mkdir()
    assert ap.promessas_sem_escrita(_banco(p2, [USER, ("assistant", "Ele é seu irmão.", None)]), DESDE) == []


def test_trecho_80_caracteres_sem_quebra(tmp_path):
    p = _banco(tmp_path, [USER, ("assistant", "Anotado!\n" + "x" * 200, None)])
    t = ap.promessas_sem_escrita(p, DESDE)[0]["trecho"]
    assert len(t) == 80 and "\n" not in t


def test_cli_ignora_antes_de_desde(tmp_path, capsys):
    p = _banco(tmp_path, [USER, PROMESSA])
    assert ap.main(["--state-db", str(p), "--desde", "2026-10-25"]) == 0
    assert capsys.readouterr().out.strip() == "0 casos"
    assert ap.main(["--state-db", str(p), "--desde", "2026-10-24"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2 and "Anotado!" in out[0] and out[-1] == "1 casos"


def test_somente_leitura(tmp_path):
    p = _banco(tmp_path, [USER, PROMESSA])
    os.utime(p, (1_700_000_000, 1_700_000_000))
    antes = p.stat().st_mtime
    time.sleep(0.01)
    ap.promessas_sem_escrita(p, DESDE)
    assert p.stat().st_mtime == antes
