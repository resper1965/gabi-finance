import inspect

from gabi.mcp import ferramentas_trab, servidor
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS


def test_ferramentas_de_trabalho_tem_escopo_trabalho():
    assert {n for n, e in ESCOPOS_FERRAMENTAS.items() if e == "trabalho"} == {"hoje_resumo", "resumo_manha", "frentes_listar", "frentes_itens"}


def test_nenhuma_ferramenta_de_trabalho_envia_apaga_ou_confirma():
    nomes = [n for n in ferramentas_trab.ESCOPOS]
    assert not [n for n in nomes if any(p in n for p in ("enviar", "send", "apagar", "delete", "confirmar", "decidir"))]
    fonte = inspect.getsource(ferramentas_trab)
    assert "insert" not in fonte.lower() and "update " not in fonte.lower() and "delete" not in fonte.lower().replace("nenhuma ferramenta envia, apaga", "")


# ---- TC.3: resumo da manhã e avisos ----
import datetime as dt
from pathlib import Path

from gabi.db import conectar, migrar
from gabi.mcp.ferramentas_trab import resumo_da_manha

AGORA = dt.datetime(2026, 10, 10, 7, 5, tzinfo=dt.timezone.utc)


def _banco(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, Path(__file__).parent.parent.parent / "migrations")
    return c


def test_resumo_tem_no_maximo_5_linhas(tmp_path):
    c = _banco(tmp_path)
    r = resumo_da_manha(c, AGORA)
    assert 1 <= len(r["linhas"]) <= 5 and r["texto"] == "\n".join(r["linhas"])


def test_resumo_comeca_por_desatualizado(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-09-01T10:00:00+00:00','2026-09-01T10:00:30+00:00','ok',1)")
    r = resumo_da_manha(c, AGORA)
    assert r["linhas"][0].startswith("⚠") and "desatualizad" in r["linhas"][0].lower()


def test_resumo_conta_agenda_emails_e_dinheiro(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into caixa_email(endereco, provedor, estado) values ('a@x.com','graph','sim')")
    c.execute("insert into evento(caixa_id, externo_id, inicio, fim, titulo) values (1,'e1','2026-10-10T14:00:00','2026-10-10T15:00:00','Reunião IONIC')")
    c.execute("insert into item_email(caixa_id, message_id, remetente, assunto, recebido_em, relevante, motivo) values (1,'<a>','c@x.com','Proposta','2026-10-10T05:00:00Z',1,'cliente')")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    txt = resumo_da_manha(c, AGORA)["texto"]
    assert "Reunião IONIC" in txt and "14:00" in txt and "1 e-mail" in txt


def test_aviso_so_e_marcado_entregue_apos_confirmacao_do_canal(tmp_path):
    from gabi.cobrar import pedidos
    c = _banco(tmp_path)
    c.execute("insert into aviso(tipo, payload, criado_em) values ('rodada_parada','{}','2026-10-10T05:00:00+00:00')")
    assert len(pedidos.avisos_pendentes(c, None)) == 1 and len(pedidos.avisos_pendentes(c, None)) == 1  # ler não tira da fila
    pedidos.marcar_entregue(c, 1)
    assert pedidos.avisos_pendentes(c, None) == []


def test_aviso_ja_enviado_pelo_telegram_direto_nao_volta_para_o_canal(tmp_path):
    from gabi.cobrar import pedidos
    c = _banco(tmp_path)
    c.execute("insert into aviso(tipo, payload, criado_em, telegram_em) values ('rodada_parada','{}','2026-10-10T05:00:00+00:00','2026-10-10T05:01:00+00:00')")
    assert pedidos.avisos_pendentes(c, None) == []
