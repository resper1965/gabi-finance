"""`email_lixeira` pelo MCP. Consome: gabi.mcp.ferramentas_agir, fixtures de tests/mcp/test_servidor.py e tests/correio/test_lixeira.py."""
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.mcp.servidor import criar_mcp
from gabi.mcp.tokens import emitir
from tests.correio.test_lixeira import Ponte, _msg
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)


@pytest.fixture
def con(banco):
    c = conectar(banco)
    c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values ('a@x.com','google','sim',1)")
    c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values ('b@ness.com','graph','sim',0)")
    c.execute("insert into email_fonte(conta, provedor, estado, lixeira) values ('c@y.com','google','sim',1)")
    yield c
    c.close()


def _ids(con):
    return {c: _msg(con, f, c) for c, f in (("g1", 1), ("g2", 1), ("n1", 2), ("y1", 3))}


def _cli(banco, correio, escopos=("trabalho",)):
    c = conectar(banco)
    tok = emitir(c, "x", list(escopos))
    c.close()
    return TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA, correio=correio), base_url=f"http://{HOST}"), tok


def _estado(banco, i):
    c = conectar(banco)
    try:
        return c.execute("select estado from email_msg where id=?", (i,)).fetchone()[0]
    finally:
        c.close()


def test_duas_contas_uma_sem_lixeira(banco, con):
    m = _ids(con)
    google, graph = Ponte(), Ponte()
    cli, tok = _cli(banco, {"google": google, "graph": graph})
    with cli:
        r = chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"], m["n1"], m["g2"]])["dados"]
    assert r["movidas"] == 2 and r["ids_movidos"] == [m["g1"], m["g2"]] and r["falhas"] == [{"id": m["n1"], "codigo": "conta_sem_lixeira"}]
    assert graph.chamadas == [] and google.chamadas == [("a@x.com", ["g1", "g2"])]
    assert _estado(banco, m["n1"]) == "classificada" and _estado(banco, m["g1"]) == "na_lixeira"


def test_ponte_fora_no_meio_do_lote(banco, con):
    m = _ids(con)
    class Dupla:  # a segunda conta falha
        def __init__(self):
            self.chamadas = []

        def lixeira(self, conta, ids):
            self.chamadas.append(conta)
            if conta == "c@y.com":
                raise ErroGoogleOAuth("caiu c@y.com")
            return {i: "ok" for i in ids}
    ponte = Dupla()
    cli, tok = _cli(banco, {"google": ponte})
    with cli:
        r = chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"], m["y1"]])["dados"]
    assert r["movidas"] == 1 and r["falhas"] == [{"id": m["y1"], "codigo": "fonte_indisponivel"}]
    assert "caiu" not in str(r) and _estado(banco, m["y1"]) == "classificada" and _estado(banco, m["g1"]) == "na_lixeira"


def test_sem_ponte_e_ja_estavam(banco, con):
    m = _ids(con)
    ja = _msg(con, 1, "j", estado="na_lixeira")
    cli, tok = _cli(banco, {})
    with cli:
        r = chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"], ja])["dados"]
    assert r["movidas"] == 0 and r["ja_estavam"] == [ja] and r["falhas"] == [{"id": m["g1"], "codigo": "fonte_indisponivel"}]
    c = conectar(banco)
    assert c.execute("select count(*) from decisao where origem='hermes'").fetchone()[0] == 0
    c.close()


def test_aceita_importante(banco, con):
    i = _msg(con, 1, "imp", classe="importante")
    cli, tok = _cli(banco, {"google": Ponte()})
    with cli:
        assert chamar(cli, tok, "email_lixeira", mensagem_ids=[i])["dados"]["movidas"] == 1


@pytest.mark.parametrize("ids", [[], list(range(1, 52)), [0], [-3]])
def test_limite_50(banco, con, ids):
    cli, tok = _cli(banco, {"google": Ponte()})
    with cli:
        assert chamar(cli, tok, "email_lixeira", mensagem_ids=ids)["erro"] == "requisicao_invalida"


def test_decisao_sem_remetente_nem_assunto(banco, con):
    m = _ids(con)
    cli, tok = _cli(banco, {"google": Ponte()})
    with cli:
        chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"], m["g2"]])
    c = conectar(banco)
    d = c.execute("select quem, o_que, origem from decisao where origem='hermes'").fetchall()
    c.close()
    assert [tuple(x) for x in d] == [("hermes", "correio: hermes moveu 2 mensagem(ns) para a lixeira", "hermes")]


def test_sem_escopo_trabalho(banco, con):
    m = _ids(con)
    cli, tok = _cli(banco, {"google": Ponte()}, escopos=("fin",))
    with cli:
        assert chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"]])["erro"] == "sem_escopo"
    assert _estado(banco, m["g1"]) == "classificada"


def test_excecao_inesperada_numa_conta_nao_impede_marcar_a_outra(banco, con):
    m = _ids(con)

    class Quebra:
        def lixeira(self, conta, ids):
            if conta == "c@y.com":
                raise RuntimeError("falha com y1@y.com")
            return {i: "ok" for i in ids}
    cli, tok = _cli(banco, {"google": Quebra()})
    with cli:
        r = chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"], m["y1"]])["dados"]
    assert r["movidas"] == 1 and r["ids_movidos"] == [m["g1"]] and r["falhas"] == [{"id": m["y1"], "codigo": "fonte_indisponivel"}]
    assert _estado(banco, m["g1"]) == "na_lixeira"


# ---------------- email_regra_lixo / email_remover_regra_lixo ----------------
def _regras(banco):
    c = conectar(banco)
    try:
        r = c.execute("select valor from parametro where chave='email.regras_lixo'").fetchone()
        return json.loads(r[0]) if r else []
    finally:
        c.close()


def test_regra_lixo_normaliza_idempotente_e_desfaz(banco, con):
    cli, tok = _cli(banco, {})
    with cli:
        r = chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="Fulano@X.com ")["dados"]
        assert r == {"regra": "fulano@x.com", "criada": True}
        assert chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="fulano@x.com")["dados"] == {"regra": "fulano@x.com", "criada": False}
        assert chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="@Spam.com")["dados"]["criada"] is True
        assert _regras(banco) == ["fulano@x.com", "@spam.com"]
        assert chamar(cli, tok, "email_remover_regra_lixo", remetente_ou_dominio="FULANO@x.com")["dados"] == {"regra": "fulano@x.com", "removida": True}
        assert chamar(cli, tok, "email_remover_regra_lixo", remetente_ou_dominio="fulano@x.com")["dados"] == {"regra": "fulano@x.com", "removida": False}
    assert _regras(banco) == ["@spam.com"]


def test_regra_lixo_sem_arroba_invalida(banco, con):
    cli, tok = _cli(banco, {})
    with cli:
        assert chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="x.com")["erro"] == "requisicao_invalida"
        assert chamar(cli, tok, "email_remover_regra_lixo", remetente_ou_dominio="x.com")["erro"] == "requisicao_invalida"
    assert _regras(banco) == []


def test_regra_lixo_limite_500(banco, con):
    con.execute("insert into parametro(chave, valor) values ('email.regras_lixo', ?)", (json.dumps([f"u{i}@x.com" for i in range(500)]),))
    con.commit()
    cli, tok = _cli(banco, {})
    with cli:
        assert chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="novo@x.com")["erro"] == "requisicao_invalida"
    assert len(_regras(banco)) == 500


def test_regra_lixo_decisao_so_o_tipo(banco, con):
    cli, tok = _cli(banco, {})
    with cli:
        chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="segredo@empresa.com")
        chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="segredo@empresa.com")  # nada mudou: sem decisão
        chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="@empresa.com")
        chamar(cli, tok, "email_remover_regra_lixo", remetente_ou_dominio="segredo@empresa.com")
        chamar(cli, tok, "email_remover_regra_lixo", remetente_ou_dominio="segredo@empresa.com")  # já não existia
    c = conectar(banco)
    d = [tuple(x) for x in c.execute("select quem, o_que, origem from decisao where origem='hermes' order by id").fetchall()]
    c.close()
    assert d == [("hermes", "correio: hermes criou regra de lixo (remetente)", "hermes"), ("hermes", "correio: hermes criou regra de lixo (dominio)", "hermes"),
                 ("hermes", "correio: hermes removeu regra de lixo (remetente)", "hermes")]
    assert "empresa" not in str(d)


def test_regra_lixo_exige_escopo_trabalho(banco, con):
    cli, tok = _cli(banco, {}, escopos=("fin",))
    with cli:
        assert chamar(cli, tok, "email_regra_lixo", remetente_ou_dominio="a@x.com")["erro"] == "sem_escopo"


# ---------------- a receber manual ----------------
def test_registrar_pelo_mcp_e_aparece_no_a_receber(banco):
    cli, tok = _cli(banco, None, ("fin",))
    with cli:
        r = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="1500,00", vencimento="2026-10-30", conta="Itaú", observacao="rateio")["dados"]
        assert r == {"id": r["id"], "pagador": "NESS", "valor": "1500.00", "vencimento": "2026-10-30", "conta": "Itaú", "observacao": "rateio", "estado": "aberto",
                     "desfazer": f"financeiro_cancelar_a_receber({r['id']}) ou Cobrar › A receber"}
        v = chamar(cli, tok, "financeiro_a_receber")["dados"]
    assert [m["id"] for m in v["manuais"]] == [r["id"]] and v["manuais"][0]["esperado"] == "1500.00" and v["totais"]["manuais"]["esperado"] == "1500.00"


def test_valor_ambiguo_pelo_mcp(banco):
    cli, tok = _cli(banco, None, ("fin",))
    with cli:
        assert chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="1.500")["erro"] == "valor_invalido"
    c = conectar(banco)
    assert c.execute("select count(*) from receber_manual").fetchone()[0] == 0


def test_cancelar_pelo_mcp(banco):
    cli, tok = _cli(banco, None, ("fin",))
    with cli:
        i = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="NESS", valor="-300,00")["dados"]["id"]
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)["dados"] == {"id": i, "estado": "cancelado"}
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)["erro"] == "conflito"
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=9999)["erro"] == "nao_encontrado"
        assert chamar(cli, tok, "financeiro_a_receber")["dados"]["manuais"] == []


def test_auditoria_origem_hermes_sem_pagador(banco):
    cli, tok = _cli(banco, None, ("fin",))
    with cli:
        i = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="Segredo Ltda", valor="777,77")["dados"]["id"]
        chamar(cli, tok, "financeiro_cancelar_a_receber", id=i)
        e = chamar(cli, tok, "financeiro_registrar_a_receber", pagador="Segredo Ltda", valor="1.500")
    c = conectar(banco)
    d = c.execute("select quem, o_que, origem from decisao where origem='hermes' order by id").fetchall()
    assert [tuple(x) for x in d] == [("hermes", f"a receber manual {i} registrado", "hermes"), ("hermes", f"a receber manual {i} cancelado", "hermes")]
    assert "Segredo" not in json.dumps(e) and "1.500" not in json.dumps(e)


def test_a_receber_manual_sem_escopo_fin(banco):
    cli, tok = _cli(banco, None, ("trabalho",))
    with cli:
        assert chamar(cli, tok, "financeiro_registrar_a_receber", pagador="X", valor="1,00")["erro"] == "sem_escopo"
        assert chamar(cli, tok, "financeiro_cancelar_a_receber", id=1)["erro"] == "sem_escopo"
