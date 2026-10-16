import datetime as dt
import fcntl
import json

from gabi.db import conectar
from gabi.reembolso_saude import __main__ as programa
from gabi.reembolso_saude.requisitos import CHAVE as CHAVE_REQ
from tests.reembolso_saude.conftest import AGORA, CHAVE, SEGREDOS, Modelo, arq, avisos, con, doc, pista, sistema  # noqa: F401

SEGUNDA_8H = dt.datetime(2026, 10, 19, 11, 0, tzinfo=dt.timezone.utc)


def _main(tmp_path, arq, p, cliente, agora=AGORA):
    return programa.main(tmp_path / "g.db", paperless=p, cliente=cliente, cofre=(arq, CHAVE), agora=agora)


def test_roda_registra_rodada_e_imprime_so_contagens(con, arq, tmp_path, capsys):
    p, _ = sistema([doc(10, "nf1")])
    assert _main(tmp_path, arq, p, Modelo({"nf1": pista("nf")})) == 0
    saida = capsys.readouterr().out
    assert saida.startswith("reembolso-saude: ") and "classificados=1" in saida
    assert not [s for s in SEGREDOS if s in saida]
    r = con.execute("select * from rodada where fonte='reembolso-saude'").fetchone()
    assert r["status"] == "ok" and r["lidos"] == 1 and r["novos"] == 1


def test_sem_chave_do_cofre_avisa_servico_falhou(con, tmp_path, capsys):
    assert programa.main(tmp_path / "g.db", paperless=object(), cliente=None, cofre=None, agora=AGORA) == 1
    assert [t for t, _ in avisos(con)] == ["servico_falhou"]
    assert "chave do cofre" in capsys.readouterr().err


def test_requisitos_invalidos_avisam_e_nao_derrubam_o_servico(con, arq, tmp_path):
    con.execute("insert into parametro(chave, valor) values (?, ?)", (CHAVE_REQ, json.dumps({"operadora": "x"})))
    p, _ = sistema([doc(10, "nf1")])
    assert _main(tmp_path, arq, p, Modelo({})) == 0
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_requisitos"]


def test_sem_modelo_avisa_uma_vez_por_dia(con, arq, tmp_path):
    p, _ = sistema([doc(10, "nf1")])
    _main(tmp_path, arq, p, None)
    _main(tmp_path, arq, p, None)
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_sem_modelo"]
    assert con.execute("select count(*) from reembolso_saude_doc").fetchone()[0] == 0


def test_segunda_de_manha_gera_a_lista(con, arq, tmp_path):
    p, _ = sistema([doc(10, "nf1")])
    _main(tmp_path, arq, p, Modelo({"nf1": pista("nf")}), agora=SEGUNDA_8H)
    tipos = [t for t, _ in avisos(con)]
    assert "reembolso_saude_semana" in tipos and "reembolso_saude_abre" in tipos


def test_outra_rodada_com_o_cofre_trancado_nao_roda(con, arq, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("gabi.familia.saude.ESPERA_TRAVA_S", 0.3)
    p, _ = sistema([doc(10, "nf1")])
    trava = open(str(arq) + ".lock", "w")
    fcntl.flock(trava, fcntl.LOCK_EX)
    try:
        assert _main(tmp_path, arq, p, Modelo({"nf1": pista("nf")})) == 0
    finally:
        trava.close()
    assert "cofre em uso" in capsys.readouterr().out and con.execute("select count(*) from reembolso_saude_doc").fetchone()[0] == 0
