import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.telegram import enviar_avisos

MIGRACOES = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 10, 15, 0, tzinfo=dt.timezone.utc)
ENV = {"TELEGRAM_BOT_TOKEN": "123:segredo", "TELEGRAM_CHAT_ID": "42"}


class Http:
    def __init__(self, status=200):
        self.status, self.chamadas = status, []

    def __call__(self, url, corpo):
        self.chamadas.append((url, corpo))
        return self.status


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _aviso(con, tipo="conta_atrasada", payload=None, quando=AGORA, lido=False, existe=True):
    if tipo == "conta_atrasada" and existe:  # a conta segue atrasada no banco (senão o aviso é obsoleto e não sai)
        ch = (payload or {"chave": "k"})["chave"]
        con.execute("insert or ignore into compromisso(id, nome, vencimento, valor_centavos, estado) values (?, 'x', '2026-10-01', 100, 'atrasado')", (ch,))
    return con.execute("insert into aviso(tipo, payload, criado_em, entregue_em) values (?,?,?,?)",
                       (tipo, json.dumps(payload or {"chave": "k", "nome": "IPTU", "vencimento": "2026-10-01", "valor": "R$ 500,00"}), quando.isoformat(),
                        AGORA.isoformat() if lido else None)).lastrowid


def test_desligado_sem_token_ou_chat_nao_envia_nada(con):
    _aviso(con)
    h = Http()
    assert enviar_avisos(con, {}, AGORA, h) == 0 and enviar_avisos(con, {"TELEGRAM_BOT_TOKEN": "x"}, AGORA, h) == 0
    assert h.chamadas == [] and con.execute("select telegram_em from aviso").fetchone()[0] is None


def test_envia_o_aviso_em_portugues_e_marca_como_enviado(con):
    _aviso(con)
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 1
    url, corpo = h.chamadas[0]
    assert url == "https://api.telegram.org/bot123:segredo/sendMessage" and corpo["chat_id"] == "42"
    assert "IPTU" in corpo["text"] and "Conta atrasada" in corpo["text"]
    assert con.execute("select telegram_em from aviso").fetchone()[0] == AGORA.isoformat()


def test_nao_reenvia_e_so_marca_apos_resposta_200(con):
    _aviso(con)
    assert enviar_avisos(con, ENV, AGORA, Http(500)) == 0
    assert con.execute("select telegram_em from aviso").fetchone()[0] is None  # tenta de novo na próxima rodada
    h = Http()
    enviar_avisos(con, ENV, AGORA, h)
    enviar_avisos(con, ENV, AGORA, h)
    assert len(h.chamadas) == 1


def test_ignora_aviso_lido_e_aviso_velho_para_nao_inundar_ao_ligar(con):
    _aviso(con, lido=True)
    _aviso(con, quando=AGORA - dt.timedelta(days=3))
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 0 and h.chamadas == []


def test_a_mensagem_nunca_leva_o_token(con):
    _aviso(con)
    h = Http()
    enviar_avisos(con, ENV, AGORA, h)
    assert "segredo" not in json.dumps(h.chamadas[0][1])


def test_um_envio_por_aviso_com_limite_por_rodada(con):
    for i in range(12):
        _aviso(con, payload={"chave": str(i), "nome": f"C{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 10  # no máximo 10 por rodada; o resto vai na próxima


def test_i1_escuta_atencao_vai_primeiro_e_nunca_e_descartada_por_idade(con):
    for i in range(12):
        _aviso(con, payload={"chave": str(i), "nome": f"C{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    velho = _aviso(con, tipo="escuta_atencao", payload={"numero": "+5511900000001", "nome": "Ana"}, quando=AGORA - dt.timedelta(days=5))
    novo = _aviso(con, tipo="escuta_atencao", payload={"numero": "+5511900000002", "nome": "Bia"})
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 10
    assert "crise" in h.chamadas[0][1]["text"] and "crise" in h.chamadas[1][1]["text"]
    enviados = {r[0] for r in con.execute("select id from aviso where telegram_em is not null")}
    assert {velho, novo} <= enviados


def test_i1_escuta_atencao_lida_nao_e_enviada(con):
    _aviso(con, tipo="escuta_atencao", payload={"numero": "+5511900000001", "nome": "Ana"}, quando=AGORA - dt.timedelta(days=5), lido=True)
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 0


# ---- aviso obsoleto não é enviado (fonte única da verdade) ----
from gabi.avisos import gerar_avisos, ainda_vale  # noqa: E402
from gabi.telegram import enviar_avisos_contagem  # noqa: E402


def _comp(con, id_, nome, venc, estado):
    con.execute("insert into compromisso(id, nome, vencimento, valor_centavos, estado) values (?,?,?,?,?)", (id_, nome, venc, 528055, estado))


def test_cenario_real_conta_paga_depois_do_aviso_nao_e_enviada_e_fecha(con):
    _comp(con, "xp:2026-10", "Cartão XP Visa Infinite", "2026-10-05", "atrasado")
    ontem = AGORA - dt.timedelta(hours=12)
    gerar_avisos(con, ontem)
    assert con.execute("select count(*) from aviso where tipo='conta_atrasada'").fetchone()[0] == 1
    con.execute("update compromisso set estado='pago'")
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 1, 0)
    assert h.chamadas == []
    r = con.execute("select telegram_em, entregue_em from aviso").fetchone()
    assert r["telegram_em"] and r["entregue_em"]  # nunca reenfileira e o painel não o mostra como pendente
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 0, 0)


def test_conta_ainda_atrasada_e_enviada(con):
    _comp(con, "xp:2026-10", "Cartão XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(hours=12))
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 0) and len(h.chamadas) == 1


def test_conta_atrasada_cujo_compromisso_sumiu_e_incerta_nao_envia_nem_fecha(con):
    _aviso(con, payload={"chave": "nao-existe", "nome": "X", "vencimento": "2026-10-01", "valor": "R$ 1,00"}, existe=False)
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 0, 1) and h.chamadas == []
    assert tuple(con.execute("select telegram_em, entregue_em from aviso").fetchone()) == (None, None)


def test_a_conferir_nao_envia_nem_fecha_e_volta_a_valer_quando_atrasado(con):
    _aviso(con, payload={"chave": "k", "nome": "X", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    con.execute("update compromisso set estado='a_conferir'")
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 0, 1) and h.chamadas == []
    assert tuple(con.execute("select telegram_em, entregue_em from aviso").fetchone()) == (None, None)
    con.execute("update compromisso set estado='atrasado'")
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 0)


def test_incerto_vencido_pela_janela_de_2_dias_expira_sem_enviar(con):
    _aviso(con, quando=AGORA - dt.timedelta(days=3))
    con.execute("update compromisso set estado='a_conferir'")
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 0, 0)


def test_debito_automatico_e_resolvido(con):
    _aviso(con)
    con.execute("update compromisso set estado='debito_automatico'")
    assert enviar_avisos_contagem(con, ENV, AGORA, Http()) == (0, 1, 0)


def _vence(con, itens):
    return _aviso(con, tipo="vence_hoje", payload={"chave": "2026-10-10", "itens": itens})


def test_vence_hoje_todos_pagos_descartado_e_com_um_aberto_enviado(con):
    _comp(con, "a:1", "Thiago", "2026-10-10", "pago")
    _comp(con, "b:1", "Suzana", "2026-10-10", "pago")
    itens = [{"nome": "Thiago", "valor": "1.00", "vencimento": "2026-10-10"}, {"nome": "Suzana", "valor": "2.00", "vencimento": "2026-10-10"}]
    _vence(con, itens)
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (0, 1, 0) and h.chamadas == []
    con.execute("update aviso set telegram_em=null, entregue_em=null")
    con.execute("update compromisso set estado='aberto' where id='b:1'")
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 0)


def test_vence_hoje_sem_itens_e_obsoleto(con):
    assert ainda_vale(con, "vence_hoje", {"chave": "x", "itens": []}) == "resolvido"


def test_cobrada_apos_cancelar_deixa_de_valer_se_assinatura_nao_esta_mais_cancelada(con):
    con.execute("insert into assinatura(estabelecimento, status, status_em) values ('X','cancelar','2026-09-20')")
    aid = con.execute("select id from assinatura").fetchone()[0]
    p = {"chave": str(aid), "nome": "X"}
    assert ainda_vale(con, "cobrada_apos_cancelar", p) == "vale"
    con.execute("update assinatura set status='manter'")
    assert ainda_vale(con, "cobrada_apos_cancelar", p) == "resolvido"


def test_outros_tipos_continuam_valendo(con):
    for t in ("rodada_parada", "escuta_parada", "lancamento_sem_conversao", "servico_falhou", "escuta_atencao", "exportacao_parada"):
        assert ainda_vale(con, t, {"chave": "k"}) == "vale"


def test_obsoletos_e_incertos_nao_contam_no_limite_de_10(con):
    for i in range(5):
        _aviso(con, payload={"chave": f"sumiu{i}", "nome": f"S{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"}, existe=False)
    for i in range(12):
        _aviso(con, payload={"chave": f"c{i}", "nome": f"C{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (10, 0, 5) and len(h.chamadas) == 10


def test_escuta_atencao_nunca_e_descartada_como_obsoleta_e_vai_primeiro(con):
    _aviso(con, payload={"chave": "sumiu", "nome": "S", "vencimento": "2026-10-01", "valor": "R$ 1,00"}, existe=False)
    _aviso(con, tipo="escuta_atencao", payload={"numero": "+5511900000001", "nome": "Ana"}, quando=AGORA - dt.timedelta(days=5))
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 1) and "crise" in h.chamadas[0][1]["text"]


def test_log_real_do_main_so_tem_contagens(tmp_path, monkeypatch, capsys):
    import runpy
    banco = tmp_path / "m.db"
    c = conectar(banco)
    migrar(c, MIGRACOES)
    c.execute("insert into aviso(tipo, payload, criado_em) values ('conta_atrasada', ?, ?)",
              (json.dumps({"chave": "sumiu", "nome": "Fulano Secreto", "vencimento": "2026-10-01", "valor": "R$ 9,99"}), dt.datetime.now(dt.timezone.utc).isoformat()))
    c.commit()
    c.close()
    monkeypatch.setenv("GABI_BANCO", str(banco))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:segredo")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    import gabi.telegram as t
    monkeypatch.setattr(t, "_http_real", lambda *a: pytest.fail("http não deve ser chamado"))
    with pytest.raises(SystemExit):
        runpy.run_module("gabi.telegram", run_name="__main__")
    out = capsys.readouterr().out
    assert "0 aviso(s) enviado(s), 0 obsoleto(s) descartado(s), 1 incerto(s)" in out
    assert "Fulano" not in out and "9,99" not in out and "segredo" not in out


def _itens(con):
    _comp(con, "a:1", "Luz", "2026-10-10", "pago")
    _comp(con, "b:1", "Luz", "2026-10-10", "aberto")   # mesmo nome, outro compromisso
    _comp(con, "c:1", "Gás", "2026-10-10", "aberto")
    return [{"id": "a:1", "nome": "Luz", "valor": "1.00", "vencimento": "2026-10-10"},
            {"id": "b:1", "nome": "Luz", "valor": "2.00", "vencimento": "2026-10-10"},
            {"id": "c:1", "nome": "Gás", "valor": "3.00", "vencimento": "2026-10-10"}]


def test_vence_hoje_parcial_texto_lista_so_os_abertos_e_distingue_por_id(con):
    _vence(con, _itens(con))
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 0)
    t = h.chamadas[0][1]["text"]
    assert "R$ 2.00" in t or "2.00" in t
    assert "1.00" not in t and "3.00" in t


def test_vence_hoje_payload_antigo_sem_id_usa_nome_e_vencimento(con):
    _comp(con, "a:1", "Thiago", "2026-10-10", "pago")
    _comp(con, "b:1", "Suzana", "2026-10-10", "aberto")
    _vence(con, [{"nome": "Thiago", "valor": "1.00", "vencimento": "2026-10-10"}, {"nome": "Suzana", "valor": "2.00", "vencimento": "2026-10-10"}])
    h = Http()
    assert enviar_avisos_contagem(con, ENV, AGORA, h) == (1, 0, 0)
    assert "Thiago" not in h.chamadas[0][1]["text"] and "Suzana" in h.chamadas[0][1]["text"]


def test_vence_hoje_entregue_em_outro_dia_com_item_atrasado_e_resolvido(con):
    _comp(con, "a:1", "Luz", "2026-10-10", "atrasado")
    _vence(con, [{"id": "a:1", "nome": "Luz", "valor": "1.00", "vencimento": "2026-10-10"}])
    assert enviar_avisos_contagem(con, ENV, AGORA, Http()) == (0, 1, 0)


def test_revalidar_devolve_estado_e_payload_atual(con):
    from gabi.avisos import revalidar
    itens = _itens(con)
    est, p = revalidar(con, "vence_hoje", {"chave": "k", "itens": itens})
    assert est == "vale" and [i["id"] for i in p["itens"]] == ["b:1", "c:1"]


def test_vence_hoje_sem_item_aberto_mas_com_a_conferir_e_incerto(con):
    _comp(con, "a:1", "Luz", "2026-10-10", "pago")
    _comp(con, "b:1", "Gás", "2026-10-10", "a_conferir")
    itens = [{"id": "a:1", "nome": "Luz", "valor": "1", "vencimento": "2026-10-10"}, {"id": "b:1", "nome": "Gás", "valor": "2", "vencimento": "2026-10-10"}]
    assert ainda_vale(con, "vence_hoje", {"chave": "k", "itens": itens}) == "incerto"
    con.execute("update compromisso set estado='pago' where id='b:1'")
    assert ainda_vale(con, "vence_hoje", {"chave": "k", "itens": itens}) == "resolvido"


def test_email_emergencial_vai_antes_dos_demais_avisos(con):
    for i in range(12):
        _aviso(con, payload={"chave": str(i), "nome": f"C{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    _aviso(con, tipo="email_emergencial", payload={"chave": "T1", "remetente": "banco@x.com", "assunto": "Boleto vence hoje", "motivo": "prazo hoje"})
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 10
    assert "banco@x.com" in h.chamadas[0][1]["text"] and "Boleto vence hoje" in h.chamadas[0][1]["text"]  # o alerta passa na frente da fila de contas
