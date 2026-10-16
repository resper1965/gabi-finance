import inspect

from gabi.mcp import ferramentas_trab, servidor
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS


def test_ferramentas_de_trabalho_tem_escopo_trabalho():
    assert {n for n, e in ESCOPOS_FERRAMENTAS.items() if e == "trabalho"} == {"agenda_listar", "email_listar", "hoje_resumo", "resumo_manha", "frentes_listar", "frentes_itens"}


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


def test_resumo_tem_um_bloco_por_assunto_separado_por_linha_em_branco(tmp_path):
    c = _banco(tmp_path)
    r = resumo_da_manha(c, AGORA)
    assert r["texto"] == "\n".join(r["linhas"])
    cabecalhos = [l for l in r["linhas"] if l.startswith(("💰", "📅", "📧"))]
    assert cabecalhos == ["💰 *Financeiro*", "📅 *Agenda*", "📧 *E-mail*"]
    assert "Saldo: sem leitura" in r["linhas"] and any(l.startswith("Previsão:") for l in r["linhas"])


def test_resumo_comeca_por_desatualizado(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-09-01T10:00:00+00:00','2026-09-01T10:00:30+00:00','ok',1)")
    r = resumo_da_manha(c, AGORA)
    assert r["linhas"][0].startswith("⚠") and "desatualizad" in r["linhas"][0].lower()


def test_resumo_conta_agenda_emails_e_dinheiro(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into caixa_email(endereco, provedor, estado) values ('a@x.com','graph','sim')")
    c.execute("insert into agenda_fonte(conta, provedor, estado) values ('a@x.com','google','sim')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (1,'e1','2026-10-10T17:00:00+00:00','2026-10-10T18:00:00+00:00','2026-10-10','2026-10-10','Reunião IONIC')")
    c.execute("insert into item_email(caixa_id, message_id, remetente, assunto, recebido_em, relevante, motivo) values (1,'<a>','c@x.com','Proposta','2026-10-10T05:00:00Z',1,'cliente')")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    txt = resumo_da_manha(c, AGORA)["texto"]
    assert "• 14:00 Reunião IONIC" in txt and "📅 *Agenda* (1)" in txt and "📧 *E-mail* (1 importante)" in txt and "Saldo: sem leitura" in txt


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


def test_resumo_desatualizado_nomeia_a_fonte_que_causa(tmp_path):
    c = _banco(tmp_path)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok',1)")
    c.execute("insert into rodada(fonte, inicio, fim, status) values ('notas-nibo','2026-10-01T05:00:00+00:00','2026-10-01T05:00:30+00:00','ok')")
    c.execute("insert into rodada(fonte, inicio, fim, status) values ('comprovantes-paperless','2026-10-10T05:00:00+00:00','2026-10-10T05:00:30+00:00','ok')")
    primeira = resumo_da_manha(c, AGORA)["linhas"][0]
    assert primeira.startswith("⚠️") and "desatualizados" in primeira and "notas-nibo" not in primeira


def test_agenda_listar_recusa_data_compacta_em_vez_de_devolver_vazio(tmp_path):
    import datetime as dt
    from gabi.db import conectar, migrar
    from gabi.mcp.ferramentas_trab import agenda_listar
    from pathlib import Path
    con = conectar(tmp_path / "t.db")
    migrar(con, Path(__file__).parent.parent.parent / "migrations")
    agora = dt.datetime(2026, 10, 16, 8, 0, tzinfo=dt.timezone.utc)
    for de, ate in [("20261011", "2026-10-12"), ("2026-10-11", "20261012"), (None, "2026-10-12")]:
        try:
            agenda_listar(con, agora, de, ate)
        except ValueError as e:
            assert "AAAA-MM-DD" in str(e)
        else:
            raise AssertionError(f"aceitou {de!r}..{ate!r}")
    assert agenda_listar(con, agora, "2026-10-11", "2026-10-12")["eventos"] == []
