"""`email_lixeira` pelo MCP. Consome: gabi.mcp.ferramentas_agir, fixtures de tests/mcp/test_servidor.py e tests/correio/test_lixeira.py."""
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
    return conectar(banco).execute("select estado from email_msg where id=?", (i,)).fetchone()[0]


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
        chamadas = []
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
    assert conectar(banco).execute("select count(*) from decisao where origem='hermes'").fetchone()[0] == 0


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
    d = conectar(banco).execute("select quem, o_que, origem from decisao where origem='hermes'").fetchall()
    assert [tuple(x) for x in d] == [("hermes", "correio: hermes moveu 2 mensagem(ns) para a lixeira", "hermes")]


def test_sem_escopo_trabalho(banco, con):
    m = _ids(con)
    cli, tok = _cli(banco, {"google": Ponte()}, escopos=("fin",))
    with cli:
        assert chamar(cli, tok, "email_lixeira", mensagem_ids=[m["g1"]])["erro"] == "sem_escopo"
    assert _estado(banco, m["g1"]) == "classificada"
