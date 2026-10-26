"""Vigia semanal (script `no_agent` do cron do Hermes, deploy/hermes/scripts/vigia_semanal.py)."""
import importlib.util
import sys
from pathlib import Path

CAMINHO = Path(__file__).resolve().parents[2] / "deploy" / "hermes" / "scripts" / "vigia_semanal.py"
_spec = importlib.util.spec_from_file_location("vigia_semanal", CAMINHO)
vs = importlib.util.module_from_spec(_spec)
_antes, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # sem __pycache__ em deploy/ (tests/test_deploy.py lê tudo como texto)
_spec.loader.exec_module(vs)
sys.dont_write_bytecode = _antes

FALHAS = """gabi-brain-correio.service loaded failed failed gabi.brain correio
systemd-networkd-wait-online.service loaded failed failed Wait for Network
hermes-gateway.service loaded failed failed Hermes
"""


def test_units_falhando_so_do_brain_e_hermes():
    assert vs.units_falhando(FALHAS) == ["gabi-brain-correio.service", "hermes-gateway.service"]
    assert vs.units_falhando("") == []


def test_ignora_unit_alheia():
    assert vs.units_falhando("systemd-networkd-wait-online.service loaded failed failed x\n") == []


def test_fontes_paradas():
    env = {"fontes": [{"nome": "open-finance", "estado": "ok"}, {"nome": "agenda", "estado": "parada"},
                      {"nome": "notas-nibo", "estado": "em_espera"}, {"nome": "correio", "estado": "erro"},
                      {"nome": "open-finance", "estado": "nao_conferida"}]}
    assert vs.fontes_paradas(env) == ["agenda", "correio"]
    assert vs.fontes_paradas({}) == []


def test_promessas_le_a_contagem():
    assert vs.promessas("03/10 10:00 s1 Anotado\n1 casos\n") == 1
    assert vs.promessas("0 casos\n") == 0
    assert vs.promessas("lixo") is None


def test_texto_tudo_ok_e_com_problemas():
    assert vs.texto([], [], 0) == "Vigia semanal: tudo ok (serviços no ar, dados em dia, 0 promessas sem escrita)."
    t = vs.texto(["gabi-brain-correio.service"], ["agenda"], 2)
    assert t.startswith("Vigia semanal:") and "gabi-brain-correio.service" in t and "agenda" in t and "2 promessas" in t
    assert "não consegui" in vs.texto([], [], None)


def test_main_sem_token_falha_curto(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vs, "ENV", tmp_path / "nao-existe.env")
    assert vs.main([]) == 1
    saida = capsys.readouterr().out.strip()
    assert saida.startswith("Falhou: vigia semanal (") and "\n" not in saida


def test_fontes_paradas_recusa_envelope_de_erro():
    import pytest
    for ruim in ({"erro": "sem_escopo"}, "x"):
        with pytest.raises(RuntimeError):
            vs.fontes_paradas(ruim)
    assert vs.fontes_paradas({"fontes": [{"estado": "parada"}, "lixo"]}) == ["?"]


def test_main_usa_ferramenta_com_todas_as_fontes(monkeypatch, capsys):
    chamadas = []
    monkeypatch.setattr(vs, "token", lambda: "t")
    monkeypatch.setattr(vs, "chamar", lambda tok, f, a: chamadas.append(f) or {"fontes": [{"nome": "open-finance", "estado": "parada"}]})
    class R:
        stdout = "0 casos\n"
    monkeypatch.setattr(vs.subprocess, "run", lambda *a, **k: R())
    assert vs.main([]) == 0 and chamadas == ["financeiro_saldo"]
    assert "dados parados: open-finance" in capsys.readouterr().out


def test_main_erro_da_ferramenta_vira_falhou(monkeypatch, capsys):
    monkeypatch.setattr(vs, "token", lambda: "t")
    monkeypatch.setattr(vs, "chamar", lambda *a: {"erro": "erro_interno"})
    assert vs.main([]) == 1 and capsys.readouterr().out.startswith("Falhou: vigia semanal (RuntimeError)")
