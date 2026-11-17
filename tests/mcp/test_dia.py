import inspect

from gabi.mcp import ferramentas_dia
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS


def test_ferramentas_de_trabalho_tem_escopo_trabalho():
    assert {n for n, e in ESCOPOS_FERRAMENTAS.items() if e == "trabalho"} == {"avisos_abertos", "resumo_manha"}


def test_nenhuma_ferramenta_de_trabalho_envia_apaga_ou_confirma():
    nomes = [n for n in ferramentas_dia.ESCOPOS]
    assert not [n for n in nomes if any(p in n for p in ("enviar", "send", "apagar", "delete", "confirmar", "decidir"))]
    fonte = inspect.getsource(ferramentas_dia)
    assert "insert" not in fonte.lower() and "update " not in fonte.lower() and "delete" not in fonte.lower().replace("nenhuma ferramenta envia, apaga", "")


# ---- TC.3: resumo da manhã e avisos ----
import datetime as dt
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.mcp.ferramentas_dia import resumo_da_manha

AGORA = dt.datetime(2026, 10, 10, 7, 5, tzinfo=dt.timezone.utc)


def _banco(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    return c


def test_resumo_e_so_o_bloco_financeiro(tmp_path):
    c = _banco(tmp_path)
    r = resumo_da_manha(c, AGORA)
    assert r["texto"] == "\n".join(r["linhas"])
    cabecalhos = [l for l in r["linhas"] if l.startswith(("💰", "📅", "📧"))]
    assert cabecalhos == ["💰 *Financeiro*"]  # agenda e e-mail saíram no corte: o resumo é só do dinheiro
    assert "Saldo: sem leitura" in r["linhas"] and any(l.startswith("Previsão:") for l in r["linhas"])


def test_resumo_comeca_por_desatualizado(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-09-01T10:00:00+00:00','2026-09-01T10:00:30+00:00','ok',1)")
    r = resumo_da_manha(c, AGORA)
    assert r["linhas"][0].startswith("⚠") and "desatualizad" in r["linhas"][0].lower()


def test_resumo_nao_traz_agenda_nem_email_mesmo_com_dado_no_banco(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    txt = resumo_da_manha(c, AGORA)["texto"]
    assert "Saldo: sem leitura" in txt and "📅" not in txt and "📧" not in txt and "⭐" not in txt


def test_resumo_desatualizado_nomeia_a_fonte_que_causa(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    c.execute("insert into rodada(fonte, inicio, fim, status) values ('notas-nibo','2026-10-01T05:00:00+00:00','2026-10-01T05:00:30+00:00','ok')")
    primeira = resumo_da_manha(c, AGORA)["linhas"][0]
    assert primeira.startswith("⚠️") and "desatualizados" in primeira and "notas-nibo" not in primeira


def test_resumo_nomeia_o_banco_parado_ha_mais_de_24h(tmp_path):
    import json
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    c.execute("insert into rodada(fonte, inicio, fim, status) values ('notas-nibo','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok')")
    c.execute("insert into parametro(chave, valor) values ('dinheiro.sync_banco', ?)", (json.dumps({"Itau": "2026-10-08T18:10:00Z"}),))
    linhas = resumo_da_manha(c, AGORA)["linhas"]
    assert linhas[0].startswith("⚠️") and linhas[1] == "Sem atualizar há mais de 24 h: Itau (desde 08/10 15:10)." and linhas[2] == ""


def test_resumo_avisa_so_a_contagem_de_decisoes_esperando(tmp_path):
    from gabi.decisoes import criar_pergunta
    c = _banco(tmp_path)
    assert not any("decisão" in l or "decisões" in l for l in resumo_da_manha(c, AGORA)["linhas"])
    criar_pergunta(c, "t", "Pergunta secreta A?", None, [{"n": 1, "rotulo": "Sim", "efeito": "registrar_nota"}], "claude", "2026-10-10T10:00:00+00:00")
    t1 = resumo_da_manha(c, AGORA)["texto"]
    assert t1.rstrip().endswith("🗳 1 decisão esperando você. Quer ver?") and "secreta" not in t1
    criar_pergunta(c, "t", "Pergunta B?", None, [{"n": 1, "rotulo": "Sim", "efeito": "registrar_nota"}], "claude", "2026-10-10T10:00:00+00:00")
    assert resumo_da_manha(c, AGORA)["texto"].rstrip().endswith("🗳 2 decisão(ões) esperando você. Quer ver?")
