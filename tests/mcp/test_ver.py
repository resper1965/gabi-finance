"""Ferramentas de leitura da Onda 2 (`contatos_buscar`). Consome: gabi.mcp.ferramentas_ver, fixtures de tests/mcp/test_servidor.py."""
import datetime as dt
import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.mcp import ferramentas_ver
from gabi.mcp.ferramentas_ver import a_receber, avisos, buscar_contatos, decisoes, empresas, regras, teams_sem_resposta
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, FONTES_DA_FERRAMENTA, criar_mcp, ferramentas_do_token
from gabi.rotas.avisos import descrever
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

TEL = "+5511993290462"


@pytest.fixture
def con(banco):
    c = conectar(banco)
    yield c
    c.close()


def _google(con, conta, tel, nome):
    con.execute("insert into contato_google(conta, telefone, nome) values (?,?,?)", (conta, tel, nome))


def test_buscar_sem_acento(con):
    _google(con, "a@x", TEL, "João Silva")
    assert buscar_contatos(con, "joao")["itens"][0]["nome"] == "João Silva"


def test_buscar_por_pedaco_do_telefone(con):
    _google(con, "a@x", TEL, "João Silva")
    itens = buscar_contatos(con, "99329")["itens"]
    assert len(itens) == 1 and itens[0]["telefones"] == [TEL]


def test_junta_google_e_graph(con):
    _google(con, "a@x", TEL, "Ana")
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness','g1','Ana N','(11) 99329-0462',?,'mobile','2026-10-01')", (TEL,))
    itens = buscar_contatos(con, "ana")["itens"]
    assert len(itens) == 1 and itens[0]["nome"] == "Ana" and itens[0]["origens"] == ["google:a@x", "graph:r@ness"]


def test_nome_do_graph_quando_google_sem_nome(con):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness','g1','Beto','x',?,'mobile','2026-10-01')", (TEL,))
    assert buscar_contatos(con, "beto")["itens"][0]["nome"] == "Beto"


def test_conta_do_graph_nas_tabelas_google_sai_como_graph(con):
    _google(con, "r@ness", TEL, "Ana Ness")  # a sincronização grava a ness também em contato_google
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness','g1','Ana N','x',?,'mobile','2026-10-01')", (TEL,))
    assert buscar_contatos(con, "ana")["itens"][0]["origens"] == ["graph:r@ness"]


def test_nome_da_conta_destino_vence(con):
    con.execute("insert into parametro(chave, valor) values ('escuta.conta_destino_contatos', '\"z@gmail\"')")
    _google(con, "a@outra", TEL, "Nome Outra")
    _google(con, "z@gmail", TEL, "Nome Gmail")
    assert buscar_contatos(con, "nome")["itens"][0]["nome"] == "Nome Gmail"


def test_graph_sem_telefone_nao_junta(con):
    for gid, nome in (("g1", "Ana Um"), ("g2", "Ana Dois")):
        con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('r@ness',?,?,'x',null,'mobile','2026-10-01')", (gid, nome))
    assert buscar_contatos(con, "ana")["itens"] == []


def test_email_entra_no_item(con):
    _google(con, "a@x", TEL, "Ana")
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values ('a@x','ana@y.com',?,'Ana')", (TEL,))
    itens = buscar_contatos(con, "ana@y")["itens"]
    assert len(itens) == 1 and itens[0]["emails"] == ["ana@y.com"] and itens[0]["telefones"] == [TEL]


def test_email_sem_telefone_vira_item_proprio(con):
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values ('a@x','zé@y.com','','Zé')")
    it = buscar_contatos(con, "zé@y")["itens"][0]
    assert it["telefones"] == [] and it["emails"] == ["zé@y.com"] and it["origens"] == ["google:a@x"]


def test_texto_curto(con):
    with pytest.raises(ValueError):
        buscar_contatos(con, " a ")


def test_sem_texto_da_o_resumo_das_duas_fontes(con):
    _google(con, "a@x", "+5511993290461", "Bia")
    _google(con, "a@x", TEL, "Ana")
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo, atualizado_em) values ('n@ness','g1','Ana N','(11) 99329-0462',?,'mobile','2026-10-01')", (TEL,))
    r = buscar_contatos(con, "", limite=1)
    assert r["total"] == 2 and r["por_origem"] == {"google:a@x": 2, "graph:n@ness": 1}
    assert [i["nome"] for i in r["itens"]] == ["Ana"]
    assert buscar_contatos(con, "  ")["total"] == 2


def test_limite(con):
    for i, t in enumerate(("+5511993290461", "+5511993290462", "+5511993290463")):
        _google(con, "a@x", t, f"Maria {i}")
    assert len(buscar_contatos(con, "maria", limite=2)["itens"]) == 2
    with pytest.raises(ValueError):
        buscar_contatos(con, "maria", limite=0)


def test_digitos_curtos_nao_casam_telefone(con):
    _google(con, "a@x", TEL, "João")
    assert buscar_contatos(con, "932")["itens"] == []


def test_contatos_buscar_sem_escopo(banco):
    c = conectar(banco)
    tok = emitir(c, "x", ["fin"])
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        assert chamar(cli, tok, "contatos_buscar", texto="ana")["erro"] == "sem_escopo"


def test_contatos_buscar_pelo_servidor(banco):
    c = conectar(banco)
    _google(c, "a@x", TEL, "João Silva")
    tok = emitir(c, "x", ["contatos"])
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        assert chamar(cli, tok, "contatos_buscar", texto="joao")["dados"]["itens"][0]["nome"] == "João Silva"


def test_escopo_hermes():
    assert "contatos" in ESCOPOS_HERMES and ESCOPOS_FERRAMENTAS["contatos_buscar"] == "contatos"
    assert "contatos_buscar" in ferramentas_do_token(ESCOPOS_HERMES)


# ---------------- as seis leituras restantes ----------------
def _nota(con, venc="2026-10-20", valor=123456):
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, vencimento, valor_liquido_centavos, importado_em, atualizado_em) "
                "values ('n1','1','2026-10-01','autorizada',?, 'FGV', ?, ?, '2026-10-01','2026-10-01')", (valor, venc, valor))


@pytest.mark.parametrize("mes", ["2026-13", "out", "2026-00", "2026-1"])
def test_a_receber_mes_invalido(con, mes):
    with pytest.raises(ValueError):
        a_receber(con, AGORA, mes)


def _sem_centavos(v):
    if isinstance(v, dict):
        return all(not k.endswith("_centavos") and _sem_centavos(x) for k, x in v.items())
    if isinstance(v, list):
        return all(_sem_centavos(x) for x in v)
    return True


def test_a_receber_em_reais(con):
    _nota(con)
    r = a_receber(con, AGORA)
    assert r["mes"] == "2026-10" and r["notas"][0]["esperado"] == "1234.56" and r["totais"]["notas"]["esperado"] == "1234.56"
    assert _sem_centavos(r)


@pytest.mark.parametrize("mes, hoje", [("2026-09", dt.date(2026, 9, 30)), ("2026-12", dt.date(2026, 12, 1)), ("2026-10", dt.date(2026, 10, 8)), ("", dt.date(2026, 10, 8))])
def test_a_receber_qual_hoje(con, monkeypatch, mes, hoje):
    vistos = []
    monkeypatch.setattr(ferramentas_ver, "a_receber_do_mes", lambda c, h: vistos.append(h) or {"mes": h.strftime("%Y-%m")})
    a_receber(con, AGORA, mes)
    assert vistos == [hoje]


def test_avisos_abertos(con):
    def aviso(tipo, payload, criado, entregue=None):
        con.execute("insert into aviso(tipo, payload, criado_em, entregue_em) values (?,?,?,?)", (tipo, payload, criado, entregue))
    p = {"banco": "C6", "desde": "2026-10-07T10:00:00+00:00"}
    aviso("banco_desatualizado", json.dumps(p), "2026-10-07T12:00:00+00:00", "2026-10-07T13:00:00+00:00")
    aviso("rodada_parada", json.dumps({"motivo": "caiu"}), "2026-10-08T12:00:00+00:00")
    aviso("rodada_parada", json.dumps({"motivo": "velho"}), "2026-09-01T12:00:00+00:00")
    r = avisos(con, AGORA)
    assert r["dias"] == 7 and [i["tipo"] for i in r["itens"]] == ["rodada_parada", "banco_desatualizado"]
    assert r["itens"][0]["entregue"] is False and r["itens"][0]["entregue_em"] is None
    assert r["itens"][1]["entregue"] is True and (r["itens"][1]["titulo"], r["itens"][1]["texto"]) == descrever("banco_desatualizado", p)


def test_aviso_ilegivel_vira_titulo_do_tipo(con):
    con.execute("insert into aviso(tipo, payload, criado_em) values ('rodada_parada','{nao é json','2026-10-08T12:00:00+00:00')")
    assert avisos(con, AGORA)["itens"][0]["titulo"] == "rodada_parada" and avisos(con, AGORA)["itens"][0]["texto"] == ""
    with pytest.raises(ValueError):
        avisos(con, AGORA, dias=91)


def _teams(con, conta, chat, para_mim, resposta=None, aviso=None, nome="Ana"):
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome, ultima_para_mim_em, minha_ultima_resposta_em, ultimo_aviso_em) values (?,?,?,?,?,?,?)",
                (conta, chat, "um_a_um", nome, para_mim, resposta, aviso))


def test_teams_pendentes(con):
    con.execute("insert into teams_fonte(conta, estado) values ('r@ness','sim')")
    con.execute("insert into teams_fonte(conta, estado) values ('o@x','nao')")
    _teams(con, "r@ness", "a", "2026-10-08T10:00:00-03:00")
    _teams(con, "r@ness", "b", "2026-10-08T10:00:00-03:00", resposta="2026-10-08T11:00:00-03:00")
    _teams(con, "o@x", "c", "2026-10-08T10:00:00-03:00")
    _teams(con, "r@ness", "d", "2026-10-08T12:00:00-03:00", aviso="2026-10-08T14:00:00-03:00", nome="Bia")
    r = teams_sem_resposta(con, AGORA)["itens"]
    assert [(i["de_nome"], i["avisado"], i["passou_do_prazo"], i["horas_uteis"]) for i in r] == [("Ana", False, True, 5.0), ("Bia", True, True, 3.0)]
    assert not {"texto", "mensagem", "corpo"} & set(r[0])


def test_regras_listar_filtra(con):
    for pad in ("IFOOD*", "UBER"):
        con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,1,'2026-10-01','r')", (pad, json.dumps({"categoria": "x"})))
    r = regras(con, AGORA, "ifood")["itens"]
    assert len(r) == 1 and r[0]["padrao"] == "IFOOD*" and r[0]["ativa"] is True and r[0]["casam"] == 0
    assert len(regras(con, AGORA)["itens"]) == 2


def test_decisoes_recentes(con):
    for q, o in (("2026-10-07T12:00:00+00:00", "Aprovou a regra do iFood"), ("2026-10-08T12:00:00+00:00", "Recusou UBER"), ("2026-06-01T12:00:00+00:00", "iFood velho")):
        con.execute("insert into decisao(quando, quem, o_que, origem) values (?,'r',?,'api')", (q, o))
    r = decisoes(con, AGORA, 30)
    assert [i["o_que"] for i in r["itens"]] == ["Recusou UBER", "Aprovou a regra do iFood"]
    assert [i["o_que"] for i in decisoes(con, AGORA, 30, "IFOOD")["itens"]] == ["Aprovou a regra do iFood"]
    for d in (0, 366):
        with pytest.raises(ValueError):
            decisoes(con, AGORA, d)


def test_empresas_listar(con):
    con.execute("insert into empresa(id, nome, cnpj, dados) values ('e2','Zeta','12.345.678/0001-90','{\"cidade\":\"SP\"}')")
    con.execute("insert into empresa(id, nome, cnpj, dados) values ('e1','Alfa','98765432000110','{quebrado')")
    r = empresas(con, AGORA)["itens"]
    assert [i["nome"] for i in r] == ["Alfa", "Zeta"] and r[0]["dados"] == {} and r[0]["cnpj"] == "98765432000110"
    assert r[1]["dados"] == {"cidade": "SP"} and r[1]["cnpj"] == "12.345.678/0001-90"


def test_ver_pelo_servidor_e_fontes(banco):
    c = conectar(banco)
    c.execute("insert into teams_fonte(conta, estado) values ('r@ness','sim')")
    _teams(c, "r@ness", "a", "2026-10-08T10:00:00-03:00")
    _nota(c)
    tok = emitir(c, "x", ["trabalho", "fin"])
    c.close()
    with TestClient(criar_mcp(banco, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as cli:
        r = chamar(cli, tok, "teams_pendentes")
        assert r["dados"]["itens"][0]["de_nome"] == "Ana" and r["desatualizado"] is False
        assert chamar(cli, tok, "financeiro_a_receber", mes="2026-10")["dados"]["notas"][0]["esperado"] == "1234.56"
        assert chamar(cli, tok, "financeiro_a_receber", mes="2026-13")["erro"] == "requisicao_invalida"
    assert FONTES_DA_FERRAMENTA["financeiro_a_receber"] is None
    assert FONTES_DA_FERRAMENTA["financeiro_registrar_a_receber"] == () and FONTES_DA_FERRAMENTA["financeiro_cancelar_a_receber"] == ()
    assert set(FONTES_DA_FERRAMENTA) == set(ESCOPOS_FERRAMENTAS)


def test_financeiro_a_receber_traz_manuais_em_reais(con):
    from gabi.cobrar import receber_manual
    receber_manual.registrar(con, pagador="NESS", valor="1500,00", quem="t", origem="cobrar", agora=AGORA)
    receber_manual.registrar(con, pagador="NESS", valor="-300,00", quem="t", origem="cobrar", agora=AGORA)
    r = a_receber(con, AGORA)
    assert [m["esperado"] for m in r["manuais"]] == ["1500.00", "-300.00"] and r["totais"]["manuais"]["esperado"] == "1200.00"
    assert _sem_centavos(r)
