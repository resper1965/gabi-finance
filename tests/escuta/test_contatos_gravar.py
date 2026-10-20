import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import contatos_gravar as g
from gabi.fontes.graph_ness import ErroGraphNess

MIGR = Path(__file__).parent.parent.parent / "migrations"
NESS = "resper@ness.com.br"
AGORA = "2026-10-20T12:00:00Z"


class FakeGraph:
    def __init__(self, ids=None, corrigir="ok", falhar_nomes=()):
        self.chamadas = []
        self._ids = list(ids or ["novo-1", "novo-2", "novo-3"])
        self._corrigir = corrigir
        self._falhar = set(falhar_nomes)

    def contato_criar(self, conta, nome, telefone):
        self.chamadas.append(("criar", conta, nome, telefone))
        if nome in self._falhar:
            raise ErroGraphNess(f"falhou para {nome} {telefone}")
        return {"id": self._ids.pop(0)}

    def contato_corrigir(self, conta, graph_id, antes, depois):
        self.chamadas.append(("corrigir", conta, graph_id, antes, depois))
        if depois["nome"] in self._falhar:
            raise RuntimeError(f"boom {depois['nome']} {depois['telefone']}")
        return {"resultado": self._corrigir}


@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    return k


def _ligar(con, valor="ligado"):
    con.execute("insert or replace into parametro(chave, valor) values ('contatos.escrita', ?)", (json.dumps(valor),))
    con.commit()


def _proposta(con, tipo="criar", estado="aprovada", nome="Fulana Silva", tel="+5511912345678", graph_id=None, nome_antes=None, tel_antes=None):
    cur = con.execute("insert into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, estado) "
                      "values (?,?,?,?,?,?,?,?,?)",
                      (tipo, NESS, graph_id, nome_antes, tel_antes, nome, tel, "whatsapp" if tipo == "criar" else "telefone_invalido", estado))
    con.commit()
    return cur.lastrowid


def _graph_linha(con, graph_id="g-1", nome="Beltrano", original="11 91234-5678 ", telefone=None, campo="mobile"):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo) values (?,?,?,?,?,?)",
                (NESS, graph_id, nome, original, telefone, campo))
    con.commit()


def _correcao(con, estado="aprovada", nome="Beltrano"):
    _graph_linha(con, nome=nome)
    return _proposta(con, tipo="corrigir", estado=estado, nome=nome, tel="+5511912345678", graph_id="g-1", nome_antes=nome, tel_antes="11 91234-5678 ")


def _estado(con, pid):
    r = con.execute("select estado, motivo, aplicada_em from contato_proposta where id=?", (pid,)).fetchone()
    return r["estado"], r["motivo"], r["aplicada_em"]


def test_escrita_nasce_desligada_e_so_liga_com_ligado(con):
    assert g.escrita_ligada(con) is False
    _ligar(con, "desligado")
    assert g.escrita_ligada(con) is False
    _ligar(con, True)
    assert g.escrita_ligada(con) is False
    _ligar(con, "ligado")
    assert g.escrita_ligada(con) is True
    con.execute("update parametro set valor='nao-json' where chave='contatos.escrita'")
    assert g.escrita_ligada(con) is False


def test_desligado_nao_grava_e_conta_simuladas(con):
    a = _proposta(con)
    b = _correcao(con)
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert r == {"aplicadas": 0, "falhas": 0, "descartadas": 0, "simuladas": 2}
    assert graph.chamadas == []
    assert _estado(con, a)[0] == "aprovada" and _estado(con, b)[0] == "aprovada"


def test_ligado_aplica_so_aprovadas(con):
    _ligar(con)
    a = _proposta(con, nome="Aprovada", tel="+5511911111111")
    p = _proposta(con, nome="Pendente", tel="+5511922222222", estado="pendente")
    rc = _proposta(con, nome="Recusada", tel="+5511933333333", estado="recusada")
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert r == {"aplicadas": 1, "falhas": 0, "descartadas": 0, "simuladas": 0}
    assert [c[2] for c in graph.chamadas] == ["Aprovada"]
    assert _estado(con, a) == ("aplicada", None, AGORA)
    assert _estado(con, p)[0] == "pendente" and _estado(con, rc)[0] == "recusada"


def test_criar_marca_aplicada_e_insere_em_contato_graph_com_o_id_devolvido(con):
    _ligar(con)
    a = _proposta(con)
    graph = FakeGraph(ids=["AAMk-novo"])
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [("criar", NESS, "Fulana Silva", "+5511912345678")]
    assert _estado(con, a) == ("aplicada", None, AGORA)
    r = con.execute("select * from contato_graph").fetchall()
    assert [(x["conta"], x["graph_id"], x["nome"], x["telefone_original"], x["telefone"], x["campo"], x["atualizado_em"]) for x in r] == \
        [(NESS, "AAMk-novo", "Fulana Silva", "+5511912345678", "+5511912345678", "mobile", AGORA)]


def test_corrigir_ok_atualiza_contato_graph(con):
    _ligar(con)
    b = _correcao(con)
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert r["aplicadas"] == 1
    assert graph.chamadas == [("corrigir", NESS, "g-1", {"nome": "Beltrano", "telefone": "11 91234-5678 "},
                               {"nome": "Beltrano", "telefone": "+5511912345678"})]
    assert _estado(con, b) == ("aplicada", None, AGORA)
    x = con.execute("select telefone_original, telefone from contato_graph where graph_id='g-1'").fetchone()
    assert tuple(x) == ("+5511912345678", "+5511912345678")


def test_contato_alterado_vira_falhou_com_motivo_contato_alterado_e_nao_fica_aprovada(con):
    _ligar(con)
    b = _correcao(con)
    graph = FakeGraph(corrigir="alterado")
    r = g.aplicar(con, graph, AGORA)
    assert r == {"aplicadas": 0, "falhas": 1, "descartadas": 1, "simuladas": 0}
    assert _estado(con, b)[:2] == ("falhou", "contato_alterado")
    x = con.execute("select telefone_original, telefone from contato_graph where graph_id='g-1'").fetchone()
    assert tuple(x) == ("11 91234-5678 ", None)


def test_corrigir_revalida_contato_graph_mudou_sem_chamar_o_graph(con):
    _ligar(con)
    b = _correcao(con)
    con.execute("update contato_graph set nome='Outro Nome' where graph_id='g-1'")
    con.commit()
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == []
    assert r["descartadas"] == 1 and r["falhas"] == 1
    assert _estado(con, b)[:2] == ("falhou", "contato_alterado")


def test_corrigir_revalida_linha_sumiu_ou_campo_nao_mobile(con):
    _ligar(con)
    b = _correcao(con)
    con.execute("update contato_graph set campo='home'")
    con.commit()
    graph = FakeGraph()
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, b)[:2] == ("falhou", "contato_alterado")


def test_criar_revalida_ja_existe_no_graph_ou_no_google(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    b = _proposta(con, nome="B", tel="+5511922222222")
    _graph_linha(con, graph_id="g-9", original="+5511911111111", telefone="+5511911111111")
    con.execute("insert into contato_google(conta, telefone, nome) values ('resper@gmail.com', '+5511922222222', 'B')")
    con.commit()
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == []
    assert r == {"aplicadas": 0, "falhas": 2, "descartadas": 0, "simuladas": 0}
    assert _estado(con, a)[:2] == ("falhou", "ja_existe") and _estado(con, b)[:2] == ("falhou", "ja_existe")


def test_erro_do_graph_em_uma_nao_aborta_as_outras(con):
    _ligar(con)
    a = _proposta(con, nome="Quebra Criar", tel="+5511911111111")
    b = _correcao(con, nome="Quebra Corrigir")
    c = _proposta(con, nome="Funciona", tel="+5511933333333")
    graph = FakeGraph(falhar_nomes={"Quebra Criar", "Quebra Corrigir"})
    r = g.aplicar(con, graph, AGORA)
    assert r == {"aplicadas": 1, "falhas": 2, "descartadas": 0, "simuladas": 0}
    for pid in (a, b):
        estado, motivo, _ = _estado(con, pid)
        assert (estado, motivo) == ("falhou", "graph_indisponivel")
        assert "Quebra" not in motivo and "+55" not in motivo and "9123" not in motivo
    assert _estado(con, c)[0] == "aplicada"
    assert con.execute("select count(*) from contato_proposta where estado='aprovada'").fetchone()[0] == 0


def _banco(tmp_path):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); k.close()
    return banco


def test_main_sem_socket_retorna_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GABI_FONTES_SOCKET", raising=False)
    assert g.main(_banco(tmp_path)) == 2


def test_main_sai_0_quando_nada_a_fazer(tmp_path, capsys):
    graph = FakeGraph()
    assert g.main(_banco(tmp_path), graph=graph) == 0
    assert graph.chamadas == []
    out = capsys.readouterr().out
    assert "contatos-gravar:" in out and "escrita=desligada" in out


def test_main_desligado_imprime_so_contagens(tmp_path, capsys):
    banco = _banco(tmp_path)
    k = conectar(banco); _proposta(k, nome="Segredo Nome", tel="+5511987654321"); k.close()
    graph = FakeGraph()
    assert g.main(banco, graph=graph) == 0
    out = capsys.readouterr()
    assert graph.chamadas == []
    assert "simuladas=1" in out.out
    assert "Segredo" not in out.out + out.err and "98765" not in out.out + out.err


def test_main_sai_1_com_graph_indisponivel_e_0_com_descartada(tmp_path, capsys):
    banco = _banco(tmp_path)
    k = conectar(banco); _ligar(k); _proposta(k, nome="Quebra", tel="+5511911111111"); k.close()
    assert g.main(banco, graph=FakeGraph(falhar_nomes={"Quebra"})) == 1
    out = capsys.readouterr()
    assert "Quebra" not in out.out + out.err and "escrita=ligada" in out.out and "falhas=1" in out.out
    banco2 = tmp_path / "n.db"
    k = conectar(banco2); migrar(k, MIGR); _ligar(k); _correcao(k); k.close()
    assert g.main(banco2, graph=FakeGraph(corrigir="alterado")) == 0
