"""Ferramentas de escrita financeira pelo MCP (a receber manual, gasto, assinatura, gastador, reembolso). Consome: gabi.mcp.ferramentas_agir, fixtures de tests/mcp/test_servidor.py."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)


def _cli(banco, escopos=("fin",)):
    c = conectar(banco)
    tok = emitir(c, "x", list(escopos))
    c.close()
    return TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}"), tok


# ---------------- a receber manual ----------------
def test_registrar_pelo_mcp_e_aparece_no_a_receber(banco):
    cli, tok = _cli(banco, ("fin",))
    with cli:
        r = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="1500,00", vencimento="2026-10-30", conta="Itaú", observacao="rateio")["dados"]
        assert r == {"id": r["id"], "pagador": "NESS", "valor": "1500.00", "vencimento": "2026-10-30", "conta": "Itaú", "observacao": "rateio", "estado": "aberto",
                     "desfazer": f"financeiro_cancelar_a_receber({r['id']}) ou Cobrar › A receber"}
        v = chamar(cli, tok, "financeiro_a_receber")["dados"]
    assert [m["id"] for m in v["manuais"]] == [r["id"]] and v["manuais"][0]["esperado"] == "1500.00" and v["totais"]["manuais"]["esperado"] == "1500.00"


def test_valor_ambiguo_pelo_mcp(banco):
    cli, tok = _cli(banco, ("fin",))
    with cli:
        assert chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="1.500")["erro"] == "valor_invalido"
    c = conectar(banco)
    assert c.execute("select count(*) from receber_manual").fetchone()[0] == 0


def test_cancelar_pelo_mcp(banco):
    cli, tok = _cli(banco, ("fin",))
    with cli:
        i = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="-300,00")["dados"]["id"]
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)["dados"] == {"id": i, "estado": "cancelado"}
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)["erro"] == "conflito"
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=9999)["erro"] == "nao_encontrado"
        assert chamar(cli, tok, "financeiro_a_receber")["dados"]["manuais"] == []


def test_auditoria_origem_hermes_sem_pagador(banco):
    cli, tok = _cli(banco, ("fin",))
    with cli:
        i = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="Segredo Ltda", valor="777,77")["dados"]["id"]
        chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)
        e = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="Segredo Ltda", valor="1.500")
    c = conectar(banco)
    d = c.execute("select quem, o_que, origem from decisao where origem='hermes' order by id").fetchall()
    assert [tuple(x) for x in d] == [("hermes", f"a receber manual {i} registrado", "hermes"), ("hermes", f"a receber manual {i} cancelado", "hermes")]
    assert "Segredo" not in json.dumps(e) and "1.500" not in json.dumps(e)


def test_a_receber_manual_sem_escopo_fin(banco):
    cli, tok = _cli(banco, ("trabalho",))
    with cli:
        assert chamar(cli, tok, "financeiro_registrar_a_receber", pagador="X", valor="1,00")["erro"] == "sem_escopo"
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=1)["erro"] == "sem_escopo"


@pytest.mark.parametrize("bruto", ["abc", "R$ 12x", "12,3,4"])
def test_valor_ilegivel_nao_ecoa_o_texto(banco, bruto):
    cli, tok = _cli(banco, ("fin",))
    with cli:
        r = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="X", valor=bruto)
    assert r["erro"] == "valor_invalido" and bruto not in json.dumps(r, ensure_ascii=False)


# ---------------- o que não é gasto e assinaturas ----------------
def _gastos(banco):
    c = conectar(banco)
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado) values (901,'bx','Itaú','BANK','itau','sim')")
    a = c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                  "values (901,'g1','2026-10-05',-976667,'Pagamento de boleto AVENUES','caixa+custo','posted')").lastrowid
    c.execute("insert into assinatura(estabelecimento) values ('NETFLIX')")
    c.execute("insert into assinatura(estabelecimento) values ('SEM PARAR')")
    c.execute("insert into assinatura(estabelecimento) values ('SEM PARAR TAG')")
    return a


def test_marcar_nao_gasto_desfazer_e_auditoria(banco):
    lid = _gastos(banco)
    cli, tok = _cli(banco, ("fin",))
    with cli:
        r = chamar(cli, tok, "financeiro_marcar_gasto", lancamento_ids=[lid], gasto="nao")["dados"]
        assert r["itens"][0]["gasto"] is False and r["itens"][0]["motivo"] == "manual"
        assert chamar(cli, tok, "financeiro_marcar_gasto", lancamento_ids=[lid], gasto="automatico")["dados"]["itens"][0]["gasto"] is True
        assert chamar(cli, tok, "financeiro_marcar_gasto", lancamento_ids=[lid], gasto="talvez")["erro"] == "requisicao_invalida"
        assert chamar(cli, tok, "financeiro_marcar_gasto", lancamento_ids=[999999], gasto="nao")["erro"] == "nao_encontrado"
    d = conectar(banco).execute("select o_que from decisao where origem='hermes' order by id").fetchall()
    assert [x[0] for x in d] == ["gastos: hermes marcou 1 lançamento(s) como gasto=nao", "gastos: hermes marcou 1 lançamento(s) como gasto=automatico"]


def test_assinatura_marcar_por_nome_ambiguo_e_desfazer(banco):
    _gastos(banco)
    cli, tok = _cli(banco, ("fin",))
    with cli:
        r = chamar(cli, tok, "assinatura_marcar", assinatura="netflix", status="nao_assinatura")["dados"]
        assert (r["nome"], r["status"], r["status_antes"], r["no_rol"]) == ("NETFLIX", "nao_assinatura", "a_conferir", False)
        assert chamar(cli, tok, "assinatura_marcar", assinatura="sem", status="manter")["erro"] == "ambiguo"
        assert chamar(cli, tok, "assinatura_marcar", assinatura="SEM PARAR", status="manter")["dados"]["nome"] == "SEM PARAR"  # nome exato desempata
        assert chamar(cli, tok, "assinatura_marcar", assinatura=str(r["id"]), status="a_conferir")["dados"]["no_rol"] is True
        assert chamar(cli, tok, "assinatura_marcar", assinatura="hbo", status="manter")["erro"] == "nao_encontrado"
        itens = chamar(cli, tok, "assinaturas_listar")["dados"]["itens"]
    assert {i["nome"]: i["status"] for i in itens} == {"NETFLIX": "a_conferir", "SEM PARAR": "manter", "SEM PARAR TAG": "a_conferir"}


def test_nao_gasto_e_assinatura_exigem_escopo_fin(banco):
    cli, tok = _cli(banco, ("trabalho",))
    with cli:
        assert chamar(cli, tok, "assinatura_marcar", assinatura="x", status="manter")["erro"] == "sem_escopo"
        assert chamar(cli, tok, "financeiro_marcar_gasto", lancamento_ids=[1], gasto="nao")["erro"] == "sem_escopo"


def test_indicar_gastador_por_nome_portador_e_auditoria(banco):
    c = conectar(banco)
    c.execute("insert or ignore into pessoa(id, nome, papel) values ('ricardo','Ricardo','titular'), ('louise','Louise','filha'), ('lucas','Lucas','outro')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, usuarios) values (930,'kk','Itaú','CREDIT','LATAM','sim','[\"ricardo\",\"louise\"]')")
    lid = c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                    "values (930,'z1','2026-10-05',-5000,'ZARA','custo','posted')").lastrowid
    c.close()
    cli, tok = _cli(banco, ("fin",))
    with cli:
        assert [i["id"] for i in chamar(cli, tok, "financeiro_lancamentos", pendente="gastador")["dados"]["itens"]] == [lid]
        r = chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="Louise")["dados"]
        assert r["itens"][0]["gastador"] == "louise"
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="Lucas")["erro"] == "nao_portador"
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="L")["erro"] == "ambiguo"
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[999999], pessoa="louise")["erro"] == "nao_encontrado"
        assert chamar(cli, tok, "financeiro_lancamentos", gastador="louise")["dados"]["itens"][0]["gastador"]["id"] == "louise"
    d = conectar(banco).execute("select o_que from decisao where origem='hermes' order by id").fetchall()
    assert [x[0] for x in d] == ["gastos: hermes indicou louise como quem gastou em 1 lançamento(s)"]


def test_indicar_gastador_nome_exato_vence_prefixo(banco):
    c = conectar(banco)
    c.execute("insert or ignore into pessoa(id, nome, papel) values ('bia','Bia','filha'), ('biaclara','Bia Clara','filha')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, usuarios) values (931,'kz','Itaú','CREDIT','X','sim','[\"bia\",\"biaclara\"]')")
    lid = c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                    "values (931,'z9','2026-10-05',-5000,'LOJA','custo','posted')").lastrowid
    c.close()
    cli, tok = _cli(banco, ("fin",))
    with cli:
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="bia")["dados"]["itens"][0]["gastador"] == "bia"
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="Bia")["dados"]["itens"][0]["gastador"] == "bia"
        assert chamar(cli, tok, "financeiro_indicar_gastador", lancamento_ids=[lid], pessoa="%")["erro"] == "nao_encontrado"


def test_marcar_reembolso_por_nome_pessoal_e_auditoria(banco):
    c = conectar(banco)
    c.execute("insert or ignore into empresa(id, nome) values ('ness','NESS Processos e Tecnologia LTDA'), ('bekaa','Bekaa Tecnologia LTDA'), "
              "('ionic-health-br','IONIC HEALTH TECHNOLOGIES S.A.'), ('ionic-health-us','IONIC Health Holding Technologies LLC')")
    c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado) values (932,'kr','Itaú','CREDIT','BLACK','sim')")
    lid = c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                    "values (932,'r1','2026-10-05',-12000,'UBER','custo','posted')").lastrowid
    c.close()
    cli, tok = _cli(banco, ("fin",))
    with cli:
        r = chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="ness")["dados"]
        assert r["itens"][0]["empresa"] == "ness" and r["empresa"] == "NESS Processos e Tecnologia LTDA"
        assert chamar(cli, tok, "financeiro_lancamentos", empresa="ness")["dados"]["itens"][0]["id"] == lid
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="ionic")["erro"] == "ambiguo"
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="ionic-health-br")["dados"]["itens"][0]["empresa"] == "ionic-health-br"
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="Bekaa")["dados"]["itens"][0]["empresa"] == "bekaa"
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="pessoal")["dados"]["itens"][0]["empresa"] is None
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[lid], empresa="acme")["erro"] == "nao_encontrado"
        assert chamar(cli, tok, "financeiro_marcar_reembolso", lancamento_ids=[999999], empresa="ness")["erro"] == "nao_encontrado"
    c = conectar(banco)
    assert tuple(c.execute("select empresa_id, empresa_origem from lancamento where id=?", (lid,)).fetchone()) == (None, None)
    d = [x[0] for x in c.execute("select o_que from decisao where origem='hermes' order by id")]
    assert d[0] == "gastos: hermes marcou 1 lançamento(s) como reembolso ness" and d[-1] == "gastos: hermes marcou 1 lançamento(s) como pessoal (sem reembolso)"
