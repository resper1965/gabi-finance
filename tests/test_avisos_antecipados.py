import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.avisos import RESOLVIDO, VALE, gerar_avisos, revalidar
from gabi.db import conectar, migrar
from gabi.rotas.avisos import descrever

MIGR = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)  # 09:00 BRT, segunda


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-12T11:00:00+00:00','2026-10-12T11:01:00+00:00','ok',1)")
    return c


def _comp(con, id_, nome, dias, valor=100000, fonte="ultimo", estado="aberto", hoje=dt.date(2026, 10, 12)):
    con.execute("insert into compromisso(id, nome, vencimento, valor_centavos, valor_fonte, estado) values (?,?,?,?,?,?)",
                (id_, nome, (hoje + dt.timedelta(days=dias)).isoformat(), valor, fonte, estado))


def _avisos(con, tipo="vence_em_breve"):
    return [json.loads(r["payload"]) for r in con.execute("select payload from aviso where tipo=? order by id", (tipo,))]


def test_avisa_o_que_vence_nos_proximos_3_dias_com_a_marca_de_estimado(con):
    _comp(con, "a", "Condomínio", 3, 352264, "ultimo", "aberto")
    _comp(con, "b", "Seguro de vida", 2, 33043, "fatura", "aberto")
    _comp(con, "c", "Enel", 1, 62888, "ultimo", "aberto"); con.execute("update compromisso set forma='debito_automatico' where id='c'")
    _comp(con, "d", "Fora da janela", 4); _comp(con, "e", "Hoje", 0); _comp(con, "f", "Já paga", 2, estado="pago"); _comp(con, "g", "Atrasada", -2, estado="atrasado")
    gerar_avisos(con, AGORA)
    av = _avisos(con)
    assert len(av) == 1 and av[0]["chave"] == "2026-10-12"
    itens = [(i["nome"], i["vencimento"], i["valor"], i["estimado"], i["debito_automatico"]) for i in av[0]["itens"]]
    assert itens == [("Enel", "2026-10-13", "628.88", True, True), ("Seguro de vida", "2026-10-14", "330.43", False, False), ("Condomínio", "2026-10-15", "3522.64", True, False)]


def test_item_sem_valor_aparece_marcado_como_estimado_sem_valor(con):
    _comp(con, "a", "Carla (reembolso)", 2, None, None, "aberto")
    gerar_avisos(con, AGORA)
    i = _avisos(con)[0]["itens"][0]
    assert i["valor"] is None and i["estimado"] is True


def test_nao_repete_o_item_ja_avisado_e_avisa_so_o_que_entra_na_janela_depois(con):
    _comp(con, "a", "Condomínio", 3)
    gerar_avisos(con, AGORA)
    gerar_avisos(con, AGORA + dt.timedelta(minutes=30))  # mesma rodada de novo no mesmo dia
    assert len(_avisos(con)) == 1
    _comp(con, "b", "Seguro", 4)  # vence em 13/10+3... entra na janela no dia seguinte
    gerar_avisos(con, AGORA + dt.timedelta(days=1))
    av = _avisos(con)
    assert len(av) == 2 and [i["nome"] for i in av[1]["itens"]] == ["Seguro"]  # o Condomínio não volta


def test_conta_que_aparece_tarde_ainda_e_avisada_se_estiver_na_janela(con):
    gerar_avisos(con, AGORA)
    assert _avisos(con) == []
    _comp(con, "a", "Boleto emitido tarde", 1, 50000, "fatura", "aberto")  # a cobrança chegou na véspera
    gerar_avisos(con, AGORA + dt.timedelta(hours=3))
    assert [i["nome"] for i in _avisos(con)[0]["itens"]] == ["Boleto emitido tarde"]


def test_antecedencia_vem_do_parametro_e_invalido_cai_no_padrao(con):
    _comp(con, "a", "A", 3); _comp(con, "b", "B", 5)
    con.execute("insert into parametro(chave, valor) values ('avisos.antecedencia_dias', '5')")
    gerar_avisos(con, AGORA)
    assert [i["nome"] for i in _avisos(con)[0]["itens"]] == ["A", "B"]
    con.execute("delete from aviso"); con.execute("update parametro set valor='\"muitos\"'")
    gerar_avisos(con, AGORA)
    assert [i["nome"] for i in _avisos(con)[0]["itens"]] == ["A"]  # 3 dias


def test_revalida_na_entrega_item_pago_sai_e_valor_confirmado_substitui_o_estimado(con):
    _comp(con, "a", "Condomínio", 3, 352264, "ultimo", "aberto"); _comp(con, "b", "Seguro", 2, 33043, "ultimo", "aberto")
    gerar_avisos(con, AGORA)
    payload = _avisos(con)[0]
    con.execute("update compromisso set estado='pago' where id='b'")
    con.execute("update compromisso set estado='aberto', valor_fonte='fatura', valor_centavos=394000 where id='a'")
    estado, atual = revalidar(con, "vence_em_breve", payload)
    assert estado == VALE and [(i["nome"], i["valor"], i["estimado"]) for i in atual["itens"]] == [("Condomínio", "3940.00", False)]
    con.execute("update compromisso set estado='pago' where id='a'")
    assert revalidar(con, "vence_em_breve", payload)[0] == RESOLVIDO


def test_aviso_cuja_conta_foi_paga_antes_de_sair_fecha_sozinho_sem_enviar(con):
    _comp(con, "a", "Condomínio", 3)
    gerar_avisos(con, AGORA)
    con.execute("update compromisso set estado='pago'")
    gerar_avisos(con, AGORA + dt.timedelta(hours=1))
    r = con.execute("select telegram_em, entregue_em from aviso where tipo='vence_em_breve'").fetchone()
    assert r["entregue_em"] is not None and r["telegram_em"] == r["entregue_em"]  # fechado, não enviado


def test_valor_diferente_so_acima_de_10_por_cento_e_uma_vez_so(con):
    _comp(con, "a", "Condomínio", 3, 352264, "ultimo", "aberto")      # chega 11,8% maior
    _comp(con, "b", "Seguro", 3, 33043, "ultimo", "aberto")           # chega 3% maior
    _comp(con, "c", "Sirlene", 2, 176602, "ultimo", "aberto")         # paga direto, 20% menor
    gerar_avisos(con, AGORA)
    con.execute("update compromisso set estado='aberto', valor_fonte='fatura', valor_centavos=394000 where id='a'")
    con.execute("update compromisso set estado='aberto', valor_fonte='fatura', valor_centavos=34000 where id='b'")
    con.execute("update compromisso set estado='pago', valor_centavos=141281 where id='c'")
    gerar_avisos(con, AGORA + dt.timedelta(hours=2))
    gerar_avisos(con, AGORA + dt.timedelta(hours=3))
    av = _avisos(con, "valor_diferente")
    assert sorted((a["nome"], a["estimado"], a["real"]) for a in av) == [("Condomínio", "3522.64", "3940.00"), ("Sirlene", "1766.02", "1412.81")]


def test_valor_diferente_nao_dispara_se_o_valor_ainda_e_estimado(con):
    _comp(con, "a", "Condomínio", 3, 352264, "ultimo", "aberto")
    gerar_avisos(con, AGORA)
    con.execute("update compromisso set valor_centavos=500000, valor_fonte='padrao' where id='a'")  # outra estimativa, não o valor real
    gerar_avisos(con, AGORA + dt.timedelta(hours=2))
    assert _avisos(con, "valor_diferente") == []


def test_descrever_os_dois_avisos(con):
    t, x = descrever("vence_em_breve", {"chave": "2026-10-12", "itens": [
        {"id": "a", "nome": "Condomínio", "vencimento": "2026-10-15", "valor": "3522.64", "estimado": True, "debito_automatico": False},
        {"id": "c", "nome": "Enel", "vencimento": "2026-10-13", "valor": "628.88", "estimado": False, "debito_automatico": True},
        {"id": "d", "nome": "Reembolso", "vencimento": "2026-10-14", "valor": None, "estimado": True, "debito_automatico": False}]})
    assert "3" in t and "15/10" in x and "Condomínio" in x and "≈" in x and "estimado" in x.lower() and "débito automático" in x and "sem valor" in x
    t, x = descrever("valor_diferente", {"chave": "a", "nome": "Condomínio", "vencimento": "2026-10-15", "estimado": "3522.64", "real": "3940.00"})
    assert "Condomínio" in t and "3.522,64" in x and "3.940,00" in x
