import json

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, ESCOPOS_HERMES, criar_mcp, ferramentas_do_token
from gabi.mcp.tokens import emitir
from tests.mcp.test_servidor import AGORA, HOST, banco, chamar  # noqa: F401  (fixtures e helpers)

NESS = "resper@ness.com.br"


class GraphFalso:
    """Só a lista viva de equipes e canais; envio não existe aqui (as ferramentas só propõem)."""

    def __init__(self, equipes=None, canais=None, falha=False):
        self.equipes = equipes if equipes is not None else [{"id": "e1", "nome": "Comercial"}, {"id": "e2", "nome": "Operações"}]
        self.canais = canais if canais is not None else {"e1": [{"id": "k1", "nome": "Geral"}, {"id": "k2", "nome": "Propostas"}]}
        self.falha, self.chamadas = falha, []

    def teams_equipes(self, conta):
        self.chamadas.append(("teams_equipes", conta))
        if self.falha:
            raise ErroGraphNess("fora do ar")
        return self.equipes

    def teams_canais(self, conta, equipe_id):
        self.chamadas.append(("teams_canais", conta, equipe_id))
        return self.canais.get(equipe_id, [])


@pytest.fixture
def banco3(banco):
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?)", (json.dumps([NESS]),))
    c.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values (?, 'graph', 'primary', 'sim')", (NESS,))
    for tel, nome, email in (("1", "João Silva", "joao@x.com"), ("2", "Maria", "maria1@x.com"), ("3", "maria", "maria2@x.com")):
        c.execute("insert into contato_google(conta, telefone, nome) values ('g@x.com',?,?)", (tel, nome))
        c.execute("insert into contato_google_email(conta, email, telefone) values ('g@x.com',?,?)", (email, tel))
    c.execute("insert into teams_fonte(conta, estado) values (?, 'sim')", (NESS,))
    c.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'c1','um_a_um','Ana Souza')", (NESS,))
    c.close()
    return banco


@pytest.fixture
def tok(banco3):
    c = conectar(banco3)
    t = {k: emitir(c, k, [k]) for k in ("envios", "fin")}
    c.close()
    return t


@pytest.fixture
def graph():
    return GraphFalso()


@pytest.fixture
def cli3(banco3, graph):
    with TestClient(criar_mcp(banco3, hosts=[HOST], relogio=lambda: AGORA, graph=graph), base_url=f"http://{HOST}") as c:
        yield c


def _propostas(banco):
    return [dict(r) for r in conectar(banco).execute("select tipo, conta, estado, conteudo from envio_proposta order by id")]


EVENTO = dict(conta=NESS, titulo="Reunião", inicio="2026-10-09T10:00", duracao_min=30, convidados=["joao silva", "Ana@X.com"])


def test_propor_evento_cria_proposta_pendente_sem_link_sem_parametro(cli3, banco3, tok):
    d = chamar(cli3, tok["envios"], "propor_evento", **EVENTO)["dados"]
    assert d["estado"] == "pendente" and d["id"] == 1 and "link" not in d and d["resumo"].startswith("Evento 'Reunião'")
    [p] = _propostas(banco3)
    assert (p["tipo"], p["estado"]) == ("evento", "pendente")
    assert json.loads(p["conteudo"])["convidados"] == ["joao@x.com", "ana@x.com"]


def test_propor_evento_traz_link_do_painel(cli3, banco3, tok):
    conectar(banco3).execute("insert into parametro(chave, valor) values ('painel.url', ?)", (json.dumps("https://painel.exemplo"),))
    assert chamar(cli3, tok["envios"], "propor_evento", **EVENTO)["dados"]["link"] == "https://painel.exemplo#envios"


def test_propor_evento_convidado_ambiguo_devolve_candidatos_e_nao_grava(cli3, banco3, tok):
    r = chamar(cli3, tok["envios"], "propor_evento", **{**EVENTO, "convidados": ["Maria"]})
    assert r["erro"] == "convidado_ambiguo"
    assert "Maria <maria1@x.com>" in r["mensagem"] and "maria <maria2@x.com>" in r["mensagem"]
    assert _propostas(banco3) == []


def test_propor_evento_conta_fora_da_lista(cli3, tok):
    assert chamar(cli3, tok["envios"], "propor_evento", **{**EVENTO, "conta": "outra@x.com"})["erro"] == "conta_nao_permitida"


def test_propor_teams_chat_cria_proposta_pendente(cli3, banco3, tok):
    d = chamar(cli3, tok["envios"], "propor_teams", texto="<b>oi</b> & tchau", chat_com="ana souza")["dados"]
    assert d["estado"] == "pendente" and d["resumo"] == "Teams: chat com Ana Souza"
    [p] = _propostas(banco3)
    assert (p["tipo"], p["conta"]) == ("teams_chat", NESS)
    assert json.loads(p["conteudo"])["texto"] == "<b>oi</b> & tchau"


def test_propor_teams_canal_resolve_na_lista_viva(cli3, banco3, tok, graph):
    d = chamar(cli3, tok["envios"], "propor_teams", texto="bom dia", equipe="comercial", canal="PROPOSTAS")["dados"]
    assert d["estado"] == "pendente" and d["resumo"] == "Teams: canal Propostas da equipe Comercial"
    c = json.loads(_propostas(banco3)[0]["conteudo"])
    assert (c["equipe_id"], c["canal_id"]) == ("e1", "k2")
    assert graph.chamadas == [("teams_equipes", NESS), ("teams_canais", NESS, "e1")]


def test_propor_teams_equipe_inexistente_ou_ambigua_da_destino_ambiguo_com_nomes(banco3, tok):
    g = GraphFalso(equipes=[{"id": "e1", "nome": "Comercial"}, {"id": "e3", "nome": "comercial"}])
    with TestClient(criar_mcp(banco3, hosts=[HOST], relogio=lambda: AGORA, graph=g), base_url=f"http://{HOST}") as c:
        r = chamar(c, tok["envios"], "propor_teams", texto="x", equipe="Comercial", canal="Geral")
        assert r["erro"] == "destino_ambiguo" and "Comercial" in r["mensagem"] and "comercial" in r["mensagem"]
        r = chamar(c, tok["envios"], "propor_teams", texto="x", equipe="Nada", canal="Geral")
        assert r["erro"] == "destino_ambiguo"
    assert _propostas(banco3) == []


def test_propor_teams_canal_inexistente_da_destino_ambiguo(cli3, banco3, tok):
    assert chamar(cli3, tok["envios"], "propor_teams", texto="x", equipe="Comercial", canal="Nada")["erro"] == "destino_ambiguo"


def test_propor_teams_chat_ambiguo_devolve_candidatos(cli3, banco3, tok):
    conectar(banco3).execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'c2','grupo','Ana Souza')", (NESS,))
    r = chamar(cli3, tok["envios"], "propor_teams", texto="x", chat_com="Ana Souza")
    assert r["erro"] == "destino_ambiguo" and "candidatos: Ana Souza; Ana Souza (grupo)" in r["mensagem"]


@pytest.mark.parametrize("args", [dict(chat_com="Ana Souza", equipe="Comercial", canal="Geral"), dict(), dict(equipe="Comercial"),
                                  dict(canal="Geral"), dict(chat_com="Ana Souza", canal="Geral")])
def test_propor_teams_exige_exatamente_um_destino(cli3, banco3, tok, args):
    assert chamar(cli3, tok["envios"], "propor_teams", texto="x", **args)["erro"] == "requisicao_invalida"
    assert _propostas(banco3) == []


@pytest.mark.parametrize("contas", [[], [NESS, "outra@ness.com.br"]])
def test_propor_teams_sem_conta_unica_da_conta_nao_permitida(cli3, banco3, tok, contas):
    c = conectar(banco3)
    c.execute("delete from teams_fonte")
    for x in contas:
        c.execute("insert into teams_fonte(conta, estado) values (?, 'sim')", (x,))
    assert chamar(cli3, tok["envios"], "propor_teams", texto="x", chat_com="Ana Souza")["erro"] == "conta_nao_permitida"


def test_propor_teams_canal_sem_graph_da_fonte_indisponivel(banco3, tok):
    with TestClient(criar_mcp(banco3, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        assert chamar(c, tok["envios"], "propor_teams", texto="x", equipe="Comercial", canal="Geral")["erro"] == "fonte_indisponivel"


def test_propor_teams_graph_fora_do_ar_da_fonte_indisponivel_sem_texto_do_provedor(banco3, tok):
    with TestClient(criar_mcp(banco3, hosts=[HOST], relogio=lambda: AGORA, graph=GraphFalso(falha=True)), base_url=f"http://{HOST}") as c:
        r = chamar(c, tok["envios"], "propor_teams", texto="x", equipe="Comercial", canal="Geral")
        assert r["erro"] == "fonte_indisponivel" and "fora do ar" not in r["mensagem"]


def test_sem_escopo_envios_devolve_sem_escopo(cli3, banco3, tok):
    assert chamar(cli3, tok["fin"], "propor_evento", **EVENTO)["erro"] == "sem_escopo"
    assert chamar(cli3, tok["fin"], "propor_teams", texto="x", chat_com="Ana Souza")["erro"] == "sem_escopo"
    assert _propostas(banco3) == []


def test_nenhuma_ferramenta_aprova_ou_envia():
    assert not [n for n in ESCOPOS_FERRAMENTAS if any(p in n for p in ("enviar", "aprovar", "confirmar"))]


def test_envios_no_hermes():
    assert {ESCOPOS_FERRAMENTAS["propor_evento"], ESCOPOS_FERRAMENTAS["propor_teams"]} == {"envios"}
    assert "envios" in ESCOPOS_HERMES and {"propor_evento", "propor_teams"} <= set(ferramentas_do_token(ESCOPOS_HERMES))


def test_docstrings_dizem_que_so_propoem(cli3, tok):
    from tests.mcp.test_servidor import rpc
    desc = {t["name"]: t["description"] for t in rpc(cli3, tok["envios"], "tools/list").json()["result"]["tools"]}
    for n in ("propor_evento", "propor_teams"):
        assert desc[n].startswith("PROPÕE") and "o envio só sai quando o Ricardo clica Enviar no painel" in desc[n]
