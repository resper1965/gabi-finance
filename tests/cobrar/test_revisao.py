"""Reproduz os achados da revisão independente da Fase 2 (09/10/2026). Cada teste falhava antes da correção."""
import base64
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.cobrar import comprovantes as cmp_, pedidos, reembolso as rb
from gabi.cobrar.lote_nibo import executar_baixa, executar_lote, montar_lote, texto_baixa
from gabi.db import conectar, migrar
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.paperless import ErroPaperless
from tests.cobrar.test_lote_nibo import NiboFalso

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
DIA = dt.date(2026, 10, 9)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")   # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj','C6','BANK','C6 PJ',1,'sim')")       # 2
    c.execute("insert into empresa(id, nome, dados) values ('ness','Ness','{\"relacao\": \"contratante\"}')")
    c.execute("insert into empresa(id, nome, dados) values ('ionic','IONIC','{\"relacao\": \"contratante\"}')")
    c.execute("insert into empresa(id, nome, dados) values ('bekaa','Bekaa','{\"relacao\": \"pj_titular\"}')")
    c.execute("insert into categoria(nome, nibo_category_id) values ('Software','cat-sw')")
    c.execute("insert into parametro(chave, valor) values ('nibo_socio_id', '\"socio\"')")
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)", (json.dumps({"canais": ["whatsapp:+5511911110000", "whatsapp:+5511922220000"], "pode_pedir": True}),))
    return c


def _l(con, i, data, valor, conta=1, empresa="bekaa", cat=1, desc="DESPESA"):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, categoria_id, status) "
                       "values (?,?,?,?,?,?,?,?, 'posted')", (conta, f"l{i}", data, valor, desc, desc, empresa, cat)).lastrowid


def _pedir(con, **kw):
    base = dict(solicitante="whatsapp:+5511911110000", canal="whatsapp", mensagem_original="paga?", descricao="Dentista", valor="150,00",
                vencimento="2026-10-20", anexo_base64=None, anexo_paperless_id=None, pix_chave=None, linha_digitavel=None, para_quem=None)
    base.update(kw)
    return pedidos.registrar(con, **base)


# ---- 1. atomicidade ----
def test_aprovar_com_beneficiario_inexistente_nao_deixa_compromisso_orfao(con):
    r = _pedir(con)
    with pytest.raises(ValueError, match="benefici"):
        pedidos.decidir(con, r.pedido_id, "aprovar", "boss", conta_id=1, beneficiario_id="fantasma")
    assert con.execute("select count(*) from compromisso_linha where id like 'pedido:%'").fetchone()[0] == 0
    assert pedidos.estado(con, r.pedido_id)["estado"] == "pendente"
    pedidos.decidir(con, r.pedido_id, "aprovar", "boss", conta_id=1, beneficiario_id="ana")  # e a nova tentativa funciona


def test_conciliar_recebimento_e_atomico(con, monkeypatch):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = rb.criar_reembolso(con, "ness"); rb.marcar_cobrado(con, rid)
    cred = _l(con, 9, "2026-10-10", 4000, conta=2, empresa="ness", cat=None)

    def quebra(*a, **k):
        raise RuntimeError("caiu no meio")
    monkeypatch.setattr(rb, "_atualizar_estado", quebra)
    with pytest.raises(RuntimeError):
        rb.conciliar_recebimento(con, "ness", cred)
    assert con.execute("select recebido_centavos from reembolso_item").fetchone()[0] == 0
    assert con.execute("select count(*) from reembolso_baixa").fetchone()[0] == 0


# ---- 2. lote com Paperless ----
def _com_comprovante(con, lid):
    cid = con.execute("insert into comprovante(paperless_id, tipo, valor_centavos, data) values (77,'comprovante_pix',10000,'2026-10-01')").lastrowid
    con.execute("insert into comprovante_vinculo(comprovante_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'x','confirmado','2026-10-01')", (cid, lid))


def test_comprovante_confirmado_sem_paperless_nao_vira_ok_sem_anexo(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    _com_comprovante(con, lid)
    nibo = NiboFalso()
    lote = montar_lote(con, DIA)
    r = executar_lote(con, lote.id, lote.texto_confirmacao, nibo, baixar_comprovante=None)
    assert (r.ok, r.erro) == (0, 1) and nibo.criacoes == 1
    lote2 = montar_lote(con, DIA)  # o item volta; o reprocesso só anexa
    r2 = executar_lote(con, lote2.id, lote2.texto_confirmacao, nibo, baixar_comprovante=lambda p: ("c.pdf", b"x"))
    assert r2.ok == 1 and nibo.criacoes == 1 and "sch-1" in nibo.anexos


def test_paperless_fora_do_ar_nao_aborta_o_lote(con):
    a, b = _l(con, 1, "2026-10-01", -10000), _l(con, 2, "2026-10-02", -5000)
    _com_comprovante(con, a)
    nibo = NiboFalso()
    lote = montar_lote(con, DIA)

    def fora(_):
        raise ErroPaperless("indisponível")
    r = executar_lote(con, lote.id, lote.texto_confirmacao, nibo, baixar_comprovante=fora)
    assert (r.ok, r.erro) == (1, 1) and f"gabi:{b}" in nibo.agendamentos  # o outro item seguiu
    assert con.execute("select estado from lote_nibo").fetchone()[0] == "executado"


def test_resposta_inesperada_do_nibo_vira_erro_do_item_nao_excecao():
    from gabi.fontes.nibo_escrita import NiboEscrita
    n = NiboEscrita("t", http=lambda *a, **k: (200, {}), http_arquivo=lambda *a, **k: (200, []))
    with pytest.raises(ErroNibo):
        n.anexar_arquivo("s1", "c.pdf", b"x")


# ---- 3. fábrica do MCP ----
def test_fabrica_do_mcp_monta_o_paperless_do_ambiente(tmp_path, monkeypatch):
    from gabi.mcp.servidor import fabrica
    monkeypatch.setenv("GABI_BANCO", str(tmp_path / "g.db"))
    monkeypatch.setenv("PAPERLESS_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    assert fabrica().paperless is not None
    monkeypatch.delenv("PAPERLESS_TOKEN")
    assert fabrica().paperless is None


# ---- 4. crédito do reembolso ----
def test_credito_antes_da_cobranca_nao_e_consumido(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = rb.criar_reembolso(con, "ness")  # ainda a_cobrar
    cred = _l(con, 9, "2026-10-10", 10000, conta=2, empresa="ness", cat=None)
    assert rb.conciliar_recebimento(con, "ness", cred).sobra_centavos == 10000
    rb.marcar_cobrado(con, rid)
    r = rb.conciliar_recebimento(con, "ness", cred)  # agora aplica: o crédito não foi gasto à toa
    assert r.casados == [1] and r.sobra_centavos == 0


def test_sobra_do_credito_pode_ser_aplicada_depois(con):
    a = _l(con, 1, "2026-10-01", -3000, empresa="ness")
    rid = rb.criar_reembolso(con, "ness"); rb.marcar_cobrado(con, rid)
    cred = _l(con, 9, "2026-10-10", 5000, conta=2, empresa="ness", cat=None)
    r = rb.conciliar_recebimento(con, "ness", cred)
    assert r.casados == [a] and r.sobra_centavos == 2000
    b = _l(con, 2, "2026-10-12", -2500, empresa="ness")
    rb.criar_reembolso(con, "ness")
    rid2 = con.execute("select max(id) from reembolso").fetchone()[0]; rb.marcar_cobrado(con, rid2)
    r2 = rb.conciliar_recebimento(con, "ness", cred)  # os 2000 que sobraram baixam o novo item
    assert r2.sobra_centavos == 0 and con.execute("select recebido_centavos from reembolso_item where lancamento_id=?", (b,)).fetchone()[0] == 2000


def test_credito_de_outra_empresa_nao_baixa(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    rid = rb.criar_reembolso(con, "ness"); rb.marcar_cobrado(con, rid)
    da_ionic = _l(con, 9, "2026-10-10", 10000, conta=2, empresa="ionic", cat=None)
    sem_empresa = _l(con, 10, "2026-10-10", 10000, conta=2, empresa=None, cat=None)
    for c in (da_ionic, sem_empresa):
        with pytest.raises(ValueError, match="empresa"):
            rb.conciliar_recebimento(con, "ness", c)


# ---- 5. baixa duplicada no Nibo ----
def test_segundo_credito_nao_baixa_de_novo_o_mesmo_agendamento(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    nibo = NiboFalso()
    lote = montar_lote(con, DIA); executar_lote(con, lote.id, lote.texto_confirmacao, nibo)
    c1 = _l(con, 9, "2026-10-12", 10000, conta=2, empresa=None, cat=None)
    c2 = _l(con, 10, "2026-10-13", 10000, conta=2, empresa=None, cat=None)
    executar_baixa(con, lid, c1, texto_baixa(con, lid, c1), nibo, account_id="c6")
    with pytest.raises(ValueError, match="já"):
        executar_baixa(con, lid, c2, texto_baixa(con, lid, c2), nibo, account_id="c6")
    assert len(nibo.baixas) == 1


# ---- 6. validação do pedido ----
@pytest.mark.parametrize("kw", [dict(vencimento="amanhã"), dict(valor=None), dict(valor="abc"), dict(para_quem="fantasma")])
def test_pedido_com_dado_ruim_e_recusado_no_registro(con, kw):
    with pytest.raises(ValueError):
        _pedir(con, **kw)
    assert con.execute("select count(*) from pedido").fetchone()[0] == 0


def test_aviso_vai_para_quem_enviou_o_pedido_e_nao_para_o_primeiro_numero(con):
    r = _pedir(con, solicitante="whatsapp:+5511922220000")
    pedidos.decidir(con, r.pedido_id, "recusar", "boss")
    assert pedidos.avisos_pendentes(con, None)[0]["payload"]["solicitante"] == "whatsapp:+5511922220000"


def test_anexo_orfao_nao_fica_quando_o_pedido_e_invalido(con):
    enviados = []
    with pytest.raises(ValueError):
        _pedir(con, vencimento="amanhã", anexo_base64=base64.b64encode(b"x").decode(), enviar_ao_paperless=lambda d, n: enviados.append(1) or 5)
    assert enviados == []  # valida antes de subir o arquivo


# ---- 7. liberação sensível ----
def _mcp_dado(con, agora=None):
    from gabi.mcp import ferramentas_prop as fp
    capturado = {}

    class Srv:
        def tool(self):
            return lambda f: capturado.setdefault(f.__name__, f) or f

    def executar(nome, fn):
        return fn(con, dt.datetime(2026, 10, 9, 12, tzinfo=dt.timezone.utc))
    fp.registrar(Srv(), executar, None)
    return capturado["pessoas_dado"]


def test_liberacao_nao_e_consumida_quando_nao_ha_valor(con):
    con.execute("update pessoa set dados=? where id='ana'", (json.dumps({}),))
    con.execute("insert into liberacao_sensivel(pessoa_id, campo, liberado_por, liberado_em) values ('ana','nascimento','boss','2026-10-09')")
    dado = _mcp_dado(con)
    assert dado("ana", "nascimento")["status"] == "sem_dado"
    assert con.execute("select usada_em from liberacao_sensivel").fetchone()[0] is None  # continua valendo


def test_liberacao_consumida_uma_unica_vez_mesmo_em_corrida(con):
    con.execute("update pessoa set dados=? where id='ana'", (json.dumps({"nascimento": "1980-01-01"}),))
    con.execute("insert into liberacao_sensivel(pessoa_id, campo, liberado_por, liberado_em) values ('ana','nascimento','boss','2026-10-09')")
    dado = _mcp_dado(con)
    assert dado("ana", "nascimento")["status"] == "liberado"
    assert dado("ana", "nascimento")["status"] == "aguardando_liberacao"


# ---- 8. paginação ----
def test_docs_com_limite_para_de_paginar(con):
    from gabi.fontes.paperless import Paperless
    from tests.cobrar.paperless_falso import PaperlessFalso
    srv = PaperlessFalso(docs=[{"id": i, "title": f"d{i}", "tags": []} for i in range(1, 11)])
    cli = Paperless("http://p", "t", http=srv)
    assert [d["id"] for d in cli.docs(page_size=2, limite=3)] == [1, 2, 3]
    assert len([c for c in srv.chamadas if c[1].startswith("/api/documents/?")]) == 2  # 2 páginas bastam, não 5


# ---- 9. vínculos concorrentes ----
def test_confirmar_retira_as_outras_propostas_do_comprovante_e_do_lancamento(con):
    a, b = _l(con, 1, "2026-10-06", -15000, empresa="ness"), _l(con, 2, "2026-10-06", -15000, empresa="ness")
    c1 = cmp_.registrar_comprovante(con, paperless_id=1, tipo="comprovante_pix", valor_centavos=15000, data="2026-10-06")
    c2 = cmp_.registrar_comprovante(con, paperless_id=2, tipo="comprovante_pix", valor_centavos=15000, data="2026-10-06")
    cmp_.propor_vinculos(con, c1); cmp_.propor_vinculos(con, c2)
    v = con.execute("select id from comprovante_vinculo where comprovante_id=? and lancamento_id=?", (c1, a)).fetchone()[0]
    cmp_.confirmar(con, v, "boss")
    est = {(r["comprovante_id"], r["lancamento_id"]): r["estado"] for r in con.execute("select * from comprovante_vinculo")}
    assert est[(c1, a)] == "confirmado"
    assert est[(c1, b)] == "rejeitado"   # o mesmo comprovante não casa com outro lançamento
    assert est[(c2, a)] == "rejeitado"   # o mesmo lançamento não fica com dois comprovantes
    assert est[(c2, b)] == "proposto"    # o resto continua disponível
