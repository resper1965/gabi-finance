import datetime as dt
import json

import pytest

from gabi.reembolso_saude import rodada
from gabi.reembolso_saude.requisitos import CHAVE as CHAVE_REQ, RequisitosInvalidos
from tests.reembolso_saude.conftest import AGORA, SEGREDOS, Modelo, arq, avisos, cofre_docs, con, doc, dump_banco, pista, rodar, sistema  # noqa: F401

COMPLETO = {"nf1": pista("nf"), "comp1": pista("comprovante")}


def _estados(arq):
    return {d["id"]: d["estado"] for d in cofre_docs(arq)}


def test_nf_e_comprovante_formam_dossie_pronto_sem_nome_no_banco(con, arq):
    p, srv = sistema([doc(10, "nf1"), doc(11, "comp1")])
    r = rodar(con, arq, p, Modelo(COMPLETO))
    assert r["novos"] == 2 and r["classificados"] == 2 and r["falhos"] == 0
    assert _estados(arq) == {10: "a_pedir", 11: "a_pedir"}
    d = con.execute("select * from reembolso_saude_dossie").fetchone()
    assert (d["id"], d["mes"], d["estado"], d["docs"], d["pronto"], json.loads(d["faltam"])) == (1, "2026-10", "a_pedir", 2, 1, [])
    assert json.loads(d["doc_ids"]) == [10, 11]
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_pronto"]
    texto = dump_banco(con)
    assert not [s for s in SEGREDOS if s in texto]  # nada de saúde no gabi.db


def test_faltando_item_avisa_abre_depois_pronto_e_so_dois_avisos(con, arq):
    p, srv = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_abre"]
    (_, payload), = avisos(con)
    assert payload["faltam"] == ["comprovante"] and payload["dossie"] == 1 and payload["mes"] == "2026-10"
    rodar(con, arq, p, m)  # nada novo: nada de aviso repetido
    assert len(avisos(con)) == 1
    srv.docs[11] = doc(11, "comp1")
    rodar(con, arq, p, m)
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_abre", "reembolso_saude_pronto"]
    rodar(con, arq, p, m)
    assert len(avisos(con)) == 2


def test_recibo_sem_nf_nao_e_reembolsavel_e_reabre_quando_a_nf_chega(con, arq):
    p, srv = sistema([doc(10, "rec1")])
    m = Modelo({"rec1": pista("recibo"), "nf1": pista("nf")})
    rodar(con, arq, p, m)
    assert _estados(arq) == {10: "sem_nf"}
    assert [t for t, _ in avisos(con)] == ["reembolso_saude_sem_requisito"] and avisos(con)[0][1]["requisito"] == "nota fiscal"
    assert con.execute("select estado from reembolso_saude_dossie").fetchone()[0] == "sem_nf"
    srv.docs[11] = doc(11, "nf1")
    rodar(con, arq, p, m)
    assert _estados(arq) == {10: "a_pedir", 11: "a_pedir"}


def test_tratamento_sem_aprovacao_e_autorizacao_vale_para_o_par(con, arq):
    p, srv = sistema([doc(10, "nf1")])
    m = Modelo({"nf1": pista("nf", "tratamento"), "aut1": pista("autorizacao", "tratamento", data="2026-09-01")})
    rodar(con, arq, p, m)
    assert _estados(arq) == {10: "sem_aprovacao"}
    srv.docs[12] = doc(12, "aut1", criado="2026-09-01")
    rodar(con, arq, p, m)
    assert _estados(arq) == {10: "a_pedir", 12: "autorizacao"}
    assert con.execute("select count(*) from reembolso_saude_dossie where estado='a_pedir'").fetchone()[0] == 1


def test_confianca_baixa_ou_tipo_ausente_vai_para_conferir(con, arq):
    p, _ = sistema([doc(10, "baixa"), doc(11, "semtipo"), doc(12, "semcaso")])
    m = Modelo({"baixa": pista("nf", confianca=0.3), "semtipo": pista(None), "semcaso": pista("nf", None)})
    r = rodar(con, arq, p, m)
    assert _estados(arq) == {10: "a_conferir", 11: "a_conferir", 12: "a_conferir"} and r["a_conferir"] == 3
    assert [t for t, _ in avisos(con)] == []  # conferir não gera aviso por dossiê; entra na lista de segunda


def test_sem_modelo_espera_e_depois_processa(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    r = rodar(con, arq, p, None)
    assert r["novos"] == 1 and r["classificados"] == 0 and r["esperando"] == 1 and r["motivo_espera"] == "modelo não configurado"
    assert con.execute("select count(*) from reembolso_saude_doc").fetchone()[0] == 0
    rodar(con, arq, p, Modelo(COMPLETO))
    assert con.execute("select estado from reembolso_saude_doc where paperless_id=10").fetchone()[0] == "classificado"


def test_falha_temporaria_conta_tentativa_e_a_oitava_vira_falhou(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    m = Modelo({}, erro=RuntimeError("Bia Souza 300.00"))
    for i in range(1, rodada.MAX_TENTATIVAS):
        rodar(con, arq, p, m)
        r = con.execute("select estado, tentativas from reembolso_saude_doc").fetchone()
        assert (r["estado"], r["tentativas"]) == ("novo", i)
    rodar(con, arq, p, m)
    r = con.execute("select estado, motivo from reembolso_saude_doc").fetchone()
    assert (r["estado"], r["motivo"]) == ("falhou", "falhas repetidas")
    assert not [s for s in SEGREDOS if s in dump_banco(con)]
    m2 = Modelo(COMPLETO)
    rodar(con, arq, p, m2)
    assert m2.chamadas == 0  # falhou não é tentado de novo


def test_sem_texto_e_resposta_invalida_falham_com_codigo_fixo(con, arq):
    p, srv = sistema([doc(10, "x", content=""), doc(11, "lixo")])
    r = rodar(con, arq, p, Modelo({"lixo": "isto não é json"}))
    assert r["falhos"] == 2
    motivos = {x["paperless_id"]: x["motivo"] for x in con.execute("select paperless_id, motivo from reembolso_saude_doc")}
    assert motivos == {10: "sem texto legível", 11: "resposta inválida"}


def test_erro_inesperado_num_documento_nao_derruba_o_lote(con, arq, monkeypatch):
    p, _ = sistema([doc(10, "nf1"), doc(11, "comp1")])
    original = rodada.cofre.gravar_doc

    def quebra(s, d):
        if d["id"] == 10:
            raise RuntimeError("Bia Souza 300.00")
        return original(s, d)

    monkeypatch.setattr(rodada.cofre, "gravar_doc", quebra)
    rodar(con, arq, p, Modelo(COMPLETO))
    m = {x["paperless_id"]: (x["estado"], x["motivo"]) for x in con.execute("select * from reembolso_saude_doc")}
    assert m == {10: ("falhou", "erro ao classificar"), 11: ("classificado", None)}
    assert set(_estados(arq)) == {11}
    assert not [s for s in SEGREDOS if s in dump_banco(con)]


def test_rodar_de_novo_nao_reclassifica(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    rodar(con, arq, p, m)
    assert m.chamadas == 1


def test_pedi_move_para_pedido_acrescenta_etiqueta_e_apaga_o_protocolo(con, arq):
    p, srv = sistema([doc(10, "nf1"), doc(11, "comp1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, protocolo, criado_em) values (1, 'pedi', 'P-998877', ?)", (AGORA.isoformat(),))
    r = rodar(con, arq, p, m)
    assert r["acoes"] == 1 and _estados(arq) == {10: "pedido", 11: "pedido"}
    a = con.execute("select * from reembolso_saude_acao").fetchone()
    assert a["resultado"] == "aplicado" and a["aplicado_em"] and a["protocolo"] is None
    assert srv.tags["gabi:reembolso-pedido"] in srv.docs[10]["tags"] and srv.tags["gabi:reembolso-pedido"] in srv.docs[11]["tags"]
    assert {d["protocolo"] for d in cofre_docs(arq)} == {"P-998877"}
    assert con.execute("select estado from reembolso_saude_dossie").fetchone()[0] == "pedido"
    assert "P-998877" not in dump_banco(con)


def test_acao_sem_documentos_ou_dossie_inexistente(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    rodar(con, arq, p, Modelo(COMPLETO))
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (99, 'pedi', ?), (1, 'recebi', ?)", (AGORA.isoformat(),) * 2)
    rodar(con, arq, p, Modelo(COMPLETO))
    assert [r["resultado"] for r in con.execute("select resultado from reembolso_saude_acao order by id")] == ["dossie_inexistente", "sem_documentos"]
    assert _estados(arq) == {10: "a_pedir"}


def _credito(con, valor, descricao="CREDITO SULAMERICA SEGUROS", data="2026-10-14"):
    con.execute("insert or ignore into conta(id, externo_id, estado) values (1, 'c1', 'sim')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (1, ?, ?, ?, ?, 'posted')",
                (f"x{valor}{data}", data, valor, descricao))


def test_credito_da_operadora_vira_recebido_e_etiqueta(con, arq):
    p, srv = sistema([doc(10, "nf1"), doc(11, "comp1")])
    m = Modelo({"nf1": pista("nf"), "comp1": pista("comprovante", valor=None)})
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'pedi', ?)", ((AGORA - dt.timedelta(days=3)).isoformat(),))
    rodar(con, arq, p, m, agora=AGORA - dt.timedelta(days=2))
    _credito(con, 25000)
    r = rodar(con, arq, p, m)
    assert r["recebidos"] == 1 and _estados(arq)[10] == "recebido" and _estados(arq)[11] == "pedido"  # só o documento com valor casa
    assert srv.tags["gabi:reembolso-recebido"] in srv.docs[10]["tags"]


def test_credito_de_outro_banco_ou_ambiguo_nao_casa(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'pedi', ?)", (AGORA.isoformat(),))
    rodar(con, arq, p, m)
    _credito(con, 10000, "PIX JOAO")
    _credito(con, 10001)
    _credito(con, 10002)
    assert rodar(con, arq, p, m)["recebidos"] == 0


def test_pedido_sem_credito_ha_mais_de_30_dias_vai_para_conferir(con, arq):
    p, _ = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'pedi', ?)", (AGORA.isoformat(),))
    rodar(con, arq, p, m)
    rodar(con, arq, p, m, agora=AGORA + dt.timedelta(days=30))
    assert _estados(arq) == {10: "pedido"}
    rodar(con, arq, p, m, agora=AGORA + dt.timedelta(days=31))
    assert _estados(arq) == {10: "a_conferir"}
    _credito(con, 25000, data="2026-11-20")
    assert rodar(con, arq, p, m, agora=AGORA + dt.timedelta(days=40))["recebidos"] == 1


def test_recebi_declarado_pelo_ricardo(con, arq):
    p, srv = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'pedi', ?)", (AGORA.isoformat(),))
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'recebi', ?)", (AGORA.isoformat(),))
    rodar(con, arq, p, m)
    assert _estados(arq) == {10: "recebido"} and srv.tags["gabi:reembolso-recebido"] in srv.docs[10]["tags"]


def test_documentos_antigos_do_gabi_fin_sao_adotados_com_o_estado_legado(con, arq):
    antigo = doc(20, "nf1", tags=(3,))   # reembolso-pedido
    novo = doc(21, "comp1", tags=(2,))   # reembolso-a-pedir
    aut = doc(22, "aut1", tags=(), tipo_nome="Autorização")
    p, _ = sistema([antigo, novo, aut])
    m = Modelo({"nf1": pista("nf"), "comp1": pista("comprovante"), "aut1": pista("autorizacao")})
    r = rodar(con, arq, p, m)
    assert r["adotados"] == 3
    assert _estados(arq) == {20: "pedido", 21: "a_pedir", 22: "autorizacao"}


def test_etiqueta_que_faltou_e_acrescentada_na_rodada_seguinte(con, arq):
    p, srv = sistema([doc(10, "nf1")])
    m = Modelo(COMPLETO)
    rodar(con, arq, p, m)
    con.execute("insert into reembolso_saude_acao(dossie_id, acao, criado_em) values (1, 'pedi', ?)", (AGORA.isoformat(),))
    original = p.etiquetar

    def falha(*a, **k):
        from gabi.fontes.paperless import ErroPaperless
        raise ErroPaperless("fora do ar")

    p.etiquetar = falha
    r = rodar(con, arq, p, m)
    assert r["etiquetas_falhas"] == 1 and _estados(arq) == {10: "pedido"}
    p.etiquetar = original
    r = rodar(con, arq, p, m)
    assert r["etiquetados"] == 1 and srv.tags["gabi:reembolso-pedido"] in srv.docs[10]["tags"]


def test_so_etiquetas_gabi_sao_acrescentadas(con, arq):
    p, srv = sistema([doc(10, "nf1"), doc(11, "comp1")])
    rodar(con, arq, p, Modelo(COMPLETO))
    patches = [c for c in srv.chamadas if c[0] == "PATCH"]
    assert patches == []  # classificar não mexe em etiqueta nenhuma


def test_requisitos_invalidos_param_a_rodada(con, arq):
    con.execute("insert into parametro(chave, valor) values (?, ?)", (CHAVE_REQ, json.dumps({"operadora": "x"})))
    p, _ = sistema([doc(10, "nf1")])
    with pytest.raises(RequisitosInvalidos):
        rodar(con, arq, p, Modelo(COMPLETO))


def test_requisito_editado_muda_o_resultado(con, arq):
    from gabi.reembolso_saude import requisitos
    req = requisitos.carregar(con)
    req["todos"] = ["comprovante"]
    con.execute("insert into parametro(chave, valor) values (?, ?)", (CHAVE_REQ, json.dumps(req)))
    p, _ = sistema([doc(10, "nf1"), doc(11, "comp1")])
    rodar(con, arq, p, Modelo(COMPLETO))
    assert con.execute("select pronto from reembolso_saude_dossie").fetchone()[0] == 1
