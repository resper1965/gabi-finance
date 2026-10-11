import base64
import json
import re
from pathlib import Path

import pytest

from gabi.cobrar.pedidos import SemEscopo, avisos_pendentes, decidir, estado, marcar_entregue, registrar
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
RAIZ = Path(__file__).parent.parent.parent / "gabi"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps({"canais": ["whatsapp:+5511911110000"], "pode_pedir": True}),))
    c.execute("insert into pessoa(id, nome, dados) values ('lia','Lia',?)", (json.dumps({"canais": ["telegram:@lia"], "pode_pedir": False}),))
    return c


def _pedir(con, **kw):
    base = dict(solicitante="whatsapp:+5511911110000", canal="whatsapp", mensagem_original="paga o dentista?", descricao="Dentista", valor="R$ 1.234,56",
                vencimento="2026-10-20", anexo_base64=None, anexo_paperless_id=None, pix_chave=None, linha_digitavel=None, para_quem=None)
    base.update(kw)
    return registrar(con, **base)


def test_pedido_de_quem_nao_pode_pedir_e_recusado(con):
    with pytest.raises(SemEscopo):
        _pedir(con, solicitante="telegram:@lia")          # cadastrada, mas sem permissão de pedir
    with pytest.raises(SemEscopo):
        _pedir(con, solicitante="whatsapp:+5500000000")   # desconhecida
    assert con.execute("select count(*) from pedido").fetchone()[0] == 0


def test_registrar_nunca_diz_que_pagou(con):
    r = _pedir(con)
    assert r.estado == "pendente" and r.texto_para_responder == "Anotado, Ana. O Ricardo vai ver."
    assert not re.search(r"pag", r.texto_para_responder, re.I)


def test_registrar_guarda_valor_em_centavos_e_o_estado_consulta(con):
    r = _pedir(con)
    e = estado(con, r.pedido_id)
    assert e["estado"] == "pendente" and e["valor_centavos"] == 123456 and e["descricao"] == "Dentista" and e["solicitante_pessoa_id"] == "ana"


def test_anexo_vai_ao_paperless_nao_ao_banco(con):
    anexo = base64.b64encode(b"%PDF-1.4 conteudo do boleto").decode()
    enviados = []
    r = _pedir(con, anexo_base64=anexo, enviar_ao_paperless=lambda dados, nome: (enviados.append((dados, nome)) or 321))
    assert enviados[0][0] == b"%PDF-1.4 conteudo do boleto"
    assert estado(con, r.pedido_id)["anexo_paperless_id"] == 321
    tudo = " ".join(str(v) for t in ("pedido", "aviso") for linha in con.execute(f"select * from {t}") for v in tuple(linha))
    assert anexo not in tudo


def test_anexo_sem_destino_paperless_e_recusado(con):
    with pytest.raises(ValueError, match="Paperless"):
        _pedir(con, anexo_base64=base64.b64encode(b"x").decode())


def test_aprovar_exige_conta_e_beneficiario_e_cria_compromisso_e_aviso(con):
    r = _pedir(con, pix_chave="dentista@pix")
    with pytest.raises(ValueError, match="conta"):
        decidir(con, r.pedido_id, "aprovar", "boss@x.com", conta_id=None, beneficiario_id="ana")
    decidir(con, r.pedido_id, "aprovar", "boss@x.com", conta_id=1, beneficiario_id="ana")
    assert estado(con, r.pedido_id)["estado"] == "aprovado"
    linha = con.execute("select * from compromisso_linha where id=?", (f"pedido:{r.pedido_id}",)).fetchone()
    assert linha["valor_padrao_centavos"] == 123456 and linha["forma"] == "pix" and linha["pix"] == "dentista@pix" and linha["vencimento"] == "dia:20"
    assert linha["valido_de"] == "2026-10" and linha["valido_ate"] == "2026-10"  # só no mês do vencimento
    av = avisos_pendentes(con, None)
    assert len(av) == 1 and av[0]["tipo"] == "pedido_aprovado" and av[0]["payload"]["canal"] == "whatsapp"
    assert av[0]["payload"]["solicitante"] == "whatsapp:+5511911110000"
    assert not re.search(r"pag", av[0]["payload"]["mensagem"], re.I)  # "na fila", nunca "paguei"


def test_aprovar_gera_aviso_para_o_canal_e_marcar_entregue_tira_da_fila(con):
    r = _pedir(con)
    decidir(con, r.pedido_id, "aprovar", "boss@x.com", conta_id=1, beneficiario_id="ana")
    marcar_entregue(con, avisos_pendentes(con, None)[0]["id"])
    assert avisos_pendentes(con, None) == []


def test_recusar_e_pedir_info_avisam_com_a_mensagem(con):
    a, b = _pedir(con), _pedir(con, descricao="Outro")
    decidir(con, a.pedido_id, "recusar", "boss@x.com", mensagem="Esse não dá.")
    decidir(con, b.pedido_id, "pedir_info", "boss@x.com", mensagem="Manda o boleto?")
    assert estado(con, a.pedido_id)["estado"] == "recusado" and estado(con, b.pedido_id)["estado"] == "info_pedida"
    msgs = sorted(x["payload"]["mensagem"] for x in avisos_pendentes(con, None))
    assert msgs == ["Esse não dá.", "Manda o boleto?"]


def test_pedido_decidido_nao_decide_de_novo(con):
    r = _pedir(con)
    decidir(con, r.pedido_id, "recusar", "boss@x.com")
    with pytest.raises(ValueError):
        decidir(con, r.pedido_id, "aprovar", "boss@x.com", conta_id=1, beneficiario_id="ana")


def test_aprovar_so_pelo_painel_nao_pelo_mcp():
    """O servidor MCP não pode importar nem chamar a decisão de pedidos (R1: só o Ricardo aprova, pelo painel)."""
    fontes = " ".join(p.read_text(encoding="utf-8") for p in (RAIZ / "mcp").rglob("*.py"))
    assert "cobrar.pedidos" not in fontes or "decidir" not in fontes
    assert not re.search(r"\bdecidir\b", fontes)


def test_pedido_aprovado_aparece_nas_contas_a_pagar_do_mes(con):
    import datetime as dt
    from zoneinfo import ZoneInfo

    from gabi.dinheiro.contas_pagar import atualizar_compromissos, contas_a_pagar
    r = _pedir(con, pix_chave="dentista@pix")
    decidir(con, r.pedido_id, "aprovar", "boss@x.com", conta_id=1, beneficiario_id="ana")
    hoje = dt.date(2026, 10, 9)
    atualizar_compromissos(con, hoje, dt.datetime(2026, 10, 9, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")))
    itens = [i for g in contas_a_pagar(con, hoje, None).values() for i in g]
    p = next(i for i in itens if i["id"].startswith(f"pedido:{r.pedido_id}"))
    assert p["valor_centavos"] == 123456 and p["vencimento"] == "2026-10-20" and p["forma"] == "pix"


def test_i2_canal_digitado_com_espacos_e_hifen_casa_normalizado(con):
    con.execute("insert into pessoa(id, nome, dados) values ('bia','Bia',?)", (json.dumps({"canais": ["whatsapp:+55 11 92222-3333"], "pode_pedir": True}),))
    r = _pedir(con, solicitante="whatsapp:+5511922223333")
    assert estado(con, r.pedido_id)["solicitante_pessoa_id"] == "bia"
    with pytest.raises(SemEscopo):
        _pedir(con, solicitante="telegram:@LIA")   # outros canais seguem exatos


@pytest.mark.parametrize("acao,kw", [("aprovar", {"conta_id": 1, "beneficiario_id": "ana"}), ("recusar", {}), ("pedir_info", {})])
def test_i11_canal_escuta_nunca_gera_mensagem_nem_aviso_ao_solicitante(con, acao, kw):
    r = _pedir(con, canal="escuta")
    decidir(con, r.pedido_id, acao, "boss@x.com", **kw)
    p = estado(con, r.pedido_id)
    assert p["estado"] in ("aprovado", "recusado", "info_pedida") and p["mensagem_ao_solicitante"] is None
    assert avisos_pendentes(con, None) == []
    assert any(f"pedido {r.pedido_id}" in o[0] for o in con.execute("select o_que from decisao"))


def test_i11_aviso_antigo_de_pedido_da_escuta_nao_sai_em_avisos_pendentes(con):
    con.execute("insert into aviso(tipo, payload, criado_em) values ('pedido_aprovado', ?, '2026-10-11T10:00:00+00:00')",
                (json.dumps({"pedido_id": 9, "canal": "escuta", "solicitante": "whatsapp:+5511911110000", "mensagem": "Anotado"}),))
    con.execute("insert into aviso(tipo, payload, criado_em) values ('rodada_parada', '{}', '2026-10-11T10:00:00+00:00')")
    assert [a["tipo"] for a in avisos_pendentes(con, None)] == ["rodada_parada"]


# ---- Hermes: avisos obsoletos não voltam (mesma revalidação do Telegram) ----
def _av(con, tipo, payload, quando="2026-10-10T10:00:00+00:00"):
    return con.execute("insert into aviso(tipo, payload, criado_em) values (?,?,?)", (tipo, json.dumps(payload), quando)).lastrowid


def _comp(con, id_, estado, nome="Luz"):
    con.execute("insert into compromisso(id, nome, vencimento, valor_centavos, estado) values (?,?, '2026-10-10', 100, ?)", (id_, nome, estado))


def test_hermes_conta_resolvida_nao_volta_e_e_fechada(con):
    _comp(con, "x:1", "pago")
    i = _av(con, "conta_atrasada", {"chave": "x:1", "nome": "Luz", "vencimento": "2026-10-10", "valor": "1.00"})
    assert avisos_pendentes(con, None) == []
    r = con.execute("select telegram_em, entregue_em from aviso where id=?", (i,)).fetchone()
    assert r["telegram_em"] and r["entregue_em"]


def test_hermes_conta_incerta_nao_volta_e_fica_aberta(con):
    _comp(con, "x:1", "a_conferir")
    i = _av(con, "conta_atrasada", {"chave": "x:1", "nome": "Luz", "vencimento": "2026-10-10", "valor": "1.00"})
    _av(con, "conta_atrasada", {"chave": "sumiu", "nome": "Y", "vencimento": "2026-10-10", "valor": "1.00"})
    assert avisos_pendentes(con, None) == []
    assert tuple(con.execute("select telegram_em, entregue_em from aviso where id=?", (i,)).fetchone()) == (None, None)


def test_hermes_conta_ainda_atrasada_volta_e_escuta_atencao_nao_e_afetada(con):
    _comp(con, "x:1", "atrasado")
    _av(con, "conta_atrasada", {"chave": "x:1", "nome": "Luz", "vencimento": "2026-10-10", "valor": "1.00"})
    _av(con, "escuta_atencao", {"numero": "+5511900000001", "nome": "Ana"})
    assert [a["tipo"] for a in avisos_pendentes(con, None)] == ["conta_atrasada", "escuta_atencao"]


def test_hermes_vence_hoje_devolve_payload_atual_so_com_itens_abertos(con):
    _comp(con, "a:1", "pago"); _comp(con, "b:1", "aberto")
    _av(con, "vence_hoje", {"chave": "2026-10-10", "itens": [{"id": "a:1", "nome": "Luz", "valor": "1", "vencimento": "2026-10-10"},
                                                            {"id": "b:1", "nome": "Luz", "valor": "2", "vencimento": "2026-10-10"}]})
    r = avisos_pendentes(con, None)
    assert [i["id"] for i in r[0]["payload"]["itens"]] == ["b:1"]
