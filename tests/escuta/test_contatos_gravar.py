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


def _antigas(r):
    """Só criar/corrigir: os tipos de limpeza têm testes próprios."""
    return {k: r[k] for k in ("criar", "corrigir")}


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
    if tipo == "criar":  # o remetente aprovado que originou a proposta (a aplicação revalida)
        con.execute("insert or ignore into escuta_remetente(numero, nome, estado) values (?,?,'aprovado')", (tel, nome))
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


# ---------------- fix 1: rodadas sobrepostas ----------------
def test_main_com_a_trava_ocupada_nao_chama_o_graph(tmp_path, capsys):
    import fcntl
    banco = _banco(tmp_path)
    k = conectar(banco); _ligar(k); a = _proposta(k); k.close()
    (tmp_path / "locks").mkdir(exist_ok=True)
    with open(tmp_path / "locks" / "contatos_gravar.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        graph = FakeGraph()
        assert g.main(banco, graph=graph) == 0
        assert graph.chamadas == []
    assert capsys.readouterr().out.strip() == "contatos-gravar: ja_em_execucao=1"
    k = conectar(banco)
    assert _estado(k, a)[0] == "aprovada"
    graph = FakeGraph()
    assert g.main(banco, graph=graph) == 0  # trava solta: a próxima rodada aplica
    assert len(graph.chamadas) == 1 and _estado(k, a)[0] == "aplicada"


class _ConProxy:
    """Conexão que delega ao sqlite real, mas levanta OperationalError nos updates cujo SQL contém `gatilho` (até `vezes` vezes)."""

    def __init__(self, real, gatilho, vezes=1, so_id=None):
        self._real, self._gatilho, self._vezes, self._so_id = real, gatilho, vezes, so_id

    def execute(self, sql, params=()):
        import sqlite3
        if self._gatilho in sql and self._vezes > 0 and (self._so_id is None or self._so_id in params):
            self._vezes -= 1
            raise sqlite3.OperationalError("database is locked")
        return self._real.execute(sql, params)

    def __getattr__(self, nome):
        return getattr(self._real, nome)


def test_aplicar_concorrente_pula_a_que_ja_nao_esta_aprovada(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    b = _proposta(con, nome="B", tel="+5511922222222")

    class GraphQueMudaB(FakeGraph):
        def contato_criar(self, conta, nome, telefone):
            con.execute("update contato_proposta set estado='aplicada' where id=?", (b,))  # outra rodada tratou B
            return super().contato_criar(conta, nome, telefone)

    graph = GraphQueMudaB()
    r = g.aplicar(con, graph, AGORA)
    assert [c[2] for c in graph.chamadas] == ["A"]
    assert r["aplicadas"] == 1 and _estado(con, a)[0] == "aplicada"


# ---------------- fix 2: erro do banco ao registrar ----------------
def test_erro_do_banco_ao_marcar_aplicada_vira_falhou_e_o_laco_segue(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    b = _proposta(con, nome="B", tel="+5511922222222")
    graph = FakeGraph(ids=["id-a", "id-b"])
    r = g.aplicar(_ConProxy(con, "set estado='aplicada'", vezes=1), graph, AGORA)
    assert r == {"aplicadas": 1, "falhas": 1, "descartadas": 0, "simuladas": 0}
    assert [c[2] for c in graph.chamadas] == ["A", "B"]  # A não é reenviada
    assert _estado(con, a)[:2] == ("falhou", "graph_indisponivel")
    assert _estado(con, b)[0] == "aplicada"
    # a transação de A foi desfeita por inteiro: nada de A em contato_graph
    assert [x["graph_id"] for x in con.execute("select graph_id from contato_graph")] == ["id-b"]


def test_erro_do_banco_tambem_ao_marcar_falhou_nao_derruba_o_laco(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    b = _proposta(con, nome="B", tel="+5511922222222")
    graph = FakeGraph(ids=["id-a", "id-b"])
    r = g.aplicar(_ConProxy(con, "update contato_proposta set estado", vezes=2, so_id=a), graph, AGORA)
    assert r["falhas"] == 1 and r["aplicadas"] == 1
    assert [c[2] for c in graph.chamadas] == ["A", "B"]
    assert _estado(con, b)[0] == "aplicada"


def test_corrigir_ok_atualiza_tambem_o_nome(con):
    _ligar(con)
    _graph_linha(con, nome="Antigo")
    _proposta(con, tipo="corrigir", nome="Novo Nome", tel="+5511912345678", graph_id="g-1", nome_antes="Antigo", tel_antes="11 91234-5678 ")
    g.aplicar(con, FakeGraph(), AGORA)
    assert con.execute("select nome from contato_graph where graph_id='g-1'").fetchone()[0] == "Novo Nome"


# ---------------- revisão final: revalidação do criar e conta fora da lista ----------------
def _contas(con, contas):
    con.execute("insert or replace into parametro(chave, valor) values ('escuta.contas_contatos', ?)", (json.dumps(contas),))
    con.commit()


@pytest.mark.parametrize("estado", ["bloqueado", "ignorado", "pendente"])
def test_criar_remetente_que_deixou_de_ser_aprovado_vira_contato_alterado(con, estado):
    _ligar(con)
    a = _proposta(con)
    con.execute("update escuta_remetente set estado=?", (estado,))
    con.commit()
    graph = FakeGraph()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, a)[:2] == ("falhou", "contato_alterado")
    assert r == {"aplicadas": 0, "falhas": 1, "descartadas": 1, "simuladas": 0}


def test_criar_remetente_sumiu_vira_contato_alterado(con):
    _ligar(con)
    a = _proposta(con)
    con.execute("delete from escuta_remetente")
    con.commit()
    graph = FakeGraph()
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, a)[:2] == ("falhou", "contato_alterado")


def test_criar_remetente_renomeado_vira_contato_alterado_e_espacos_nao_contam(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    b = _proposta(con, nome="B", tel="+5511922222222")
    con.execute("update escuta_remetente set nome='Outro' where numero='+5511911111111'")
    con.execute("update escuta_remetente set nome='  B  ' where numero='+5511922222222'")
    con.commit()
    graph = FakeGraph()
    g.aplicar(con, graph, AGORA)
    assert [c[2] for c in graph.chamadas] == ["B"]
    assert _estado(con, a)[:2] == ("falhou", "contato_alterado") and _estado(con, b)[0] == "aplicada"


@pytest.mark.parametrize("tipo", ["criar", "corrigir"])
def test_conta_fora_da_lista_de_contas_vira_contato_alterado_sem_chamar_o_graph(con, tipo):
    _ligar(con)
    pid = _proposta(con) if tipo == "criar" else _correcao(con)
    _contas(con, ["resper@gmail.com"])
    graph = FakeGraph()
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, pid)[:2] == ("falhou", "contato_alterado")


def test_ponta_a_ponta_sync_gerar_aprovar_aplicar_corrige_celular_antigo(con):
    from gabi.escuta import contatos as c
    from gabi.escuta import contatos_propostas as cp
    itens = [{"nome": "Beltrano", "telefone": "11 9999-0000", "graph_id": "AAMk0001", "campo": "mobile"}]
    c.sincronizar(con, c.contas_contatos(con), lambda conta: list(itens) if conta == NESS else [])
    assert _antigas(cp.gerar(con, AGORA)) == {"criar": 0, "corrigir": 1}
    (pid,) = [r["id"] for r in cp.listar(con, "pendente")]
    assert cp.aprovar_correcoes(con, "ricardo", AGORA, [pid]) == 1
    _ligar(con)
    graph = FakeGraph()
    assert g.aplicar(con, graph, AGORA)["aplicadas"] == 1
    assert graph.chamadas == [("corrigir", NESS, "AAMk0001", {"nome": "Beltrano", "telefone": "11 9999-0000"},
                               {"nome": "Beltrano", "telefone": "+5511999990000"})]
    linha = con.execute("select telefone_original, telefone from contato_graph where graph_id='AAMk0001'").fetchone()
    assert tuple(linha) == ("+5511999990000", "+5511999990000")
    assert _antigas(cp.gerar(con, AGORA)) == {"criar": 0, "corrigir": 0}
    # e a próxima sincronização, com o Graph já corrigido, também não gera nada
    c.sincronizar(con, c.contas_contatos(con), lambda conta: [{**itens[0], "telefone": "+5511999990000"}] if conta == NESS else [])
    assert _antigas(cp.gerar(con, AGORA)) == {"criar": 0, "corrigir": 0}


# ---------------- limpeza (ADR-021) ----------------
class FakeLimpeza(FakeGraph):
    def __init__(self, resultado="ok", erro=False):
        super().__init__()
        self._resultado, self._erro = resultado, erro

    def _responde(self, *chamada):
        self.chamadas.append(chamada)
        if self._erro:
            raise ErroGraphNess("graph fora")
        return self._resultado if isinstance(self._resultado, dict) else {"resultado": self._resultado}

    def contato_renomear(self, conta, graph_id, nome_antes, nome_depois):
        return self._responde("renomear", conta, graph_id, nome_antes, nome_depois)

    def contato_apagar_telefone(self, conta, graph_id, campo, telefone_antes):
        return self._responde("apagar_telefone", conta, graph_id, campo, telefone_antes)

    def contato_apagar(self, conta, graph_id, nome_antes, telefone_antes):
        return self._responde("apagar", conta, graph_id, nome_antes, telefone_antes)


def _limpa(con, tipo, nome_antes, nome_depois, tel_antes, gid="g-1", estado="aprovada"):
    cur = con.execute("insert into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, estado) "
                      "values (?,?,?,?,?,?,'',?,?)", (tipo, NESS, gid, nome_antes, tel_antes, nome_depois, "nome_sujo", estado))
    con.commit()
    return cur.lastrowid


def _linhas_graph(con):
    return [tuple(r) for r in con.execute("select graph_id, nome, telefone_original, telefone from contato_graph order by graph_id, telefone_original")]


def _preparar(con, tipo):
    """Contato local + proposta aprovada de cada tipo de limpeza. Devolve (id da proposta, chamada esperada ao Graph)."""
    _ligar(con)
    if tipo == "corrigir_nome":
        _graph_linha(con, nome="José⁹", original="+55 11 91234-5678", telefone="+5511912345678")
        return _limpa(con, tipo, "José⁹", "José", None), ("renomear", NESS, "g-1", "José⁹", "José")
    if tipo == "apagar_telefone":
        _graph_linha(con, nome="Ana", original="12345", telefone=None, campo="home")
        return _limpa(con, tipo, "Ana", "Ana", "12345"), ("apagar_telefone", NESS, "g-1", "home", "12345")
    _graph_linha(con, nome="U", original="+55 11 94733-8256", telefone="+5511947338256")
    return _limpa(con, tipo, "U", "U", "+5511947338256"), ("apagar", NESS, "g-1", "U", "+55 11 94733-8256")


TIPOS_LIMPEZA = ["corrigir_nome", "apagar_telefone", "apagar_contato"]


@pytest.mark.parametrize("tipo", TIPOS_LIMPEZA)
def test_limpeza_ok_grava_local_e_marca_aplicada(con, tipo):
    pid, chamada = _preparar(con, tipo)
    graph = FakeLimpeza()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [chamada] and r["aplicadas"] == 1 and _estado(con, pid)[0] == "aplicada"
    esperado = {"corrigir_nome": [("g-1", "José", "+55 11 91234-5678", "+5511912345678")], "apagar_telefone": [], "apagar_contato": []}[tipo]
    assert _linhas_graph(con) == esperado


@pytest.mark.parametrize("tipo", TIPOS_LIMPEZA)
def test_limpeza_contato_mudou_localmente_nao_chama_o_graph(con, tipo):
    pid, _ = _preparar(con, tipo)
    con.execute("update contato_graph set nome='Mudou'" if tipo != "apagar_telefone" else "update contato_graph set telefone_original='999'")
    con.commit()
    graph = FakeLimpeza()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and r["falhas"] == 1 and r["descartadas"] == 1 and _estado(con, pid)[:2] == ("falhou", "contato_alterado")


@pytest.mark.parametrize("tipo", TIPOS_LIMPEZA)
def test_limpeza_graph_devolve_alterado(con, tipo):
    pid, _ = _preparar(con, tipo)
    before = _linhas_graph(con)
    r = g.aplicar(con, FakeLimpeza("alterado"), AGORA)
    assert _estado(con, pid)[:2] == ("falhou", "contato_alterado") and r["descartadas"] == 1 and _linhas_graph(con) == before


@pytest.mark.parametrize("tipo", TIPOS_LIMPEZA)
@pytest.mark.parametrize("falha", ["erro", {"resultado": "talvez"}])
def test_limpeza_graph_indisponivel(con, tipo, falha):
    pid, _ = _preparar(con, tipo)
    graph = FakeLimpeza(falha if isinstance(falha, dict) else "ok", erro=falha == "erro")
    r = g.aplicar(con, graph, AGORA)
    assert _estado(con, pid)[:2] == ("falhou", "graph_indisponivel") and r["falhas"] == 1 and r["descartadas"] == 0


@pytest.mark.parametrize("tipo", TIPOS_LIMPEZA)
def test_limpeza_desligado_so_simula(con, tipo):
    pid, _ = _preparar(con, tipo)
    _ligar(con, "desligado")
    graph = FakeLimpeza()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and r["simuladas"] == 1 and _estado(con, pid)[0] == "aprovada"


def test_apagar_telefone_sem_campo_e_alterado(con):
    _ligar(con)
    _graph_linha(con, nome="Ana", original="12345", telefone=None, campo=None)
    pid = _limpa(con, "apagar_telefone", "Ana", "Ana", "12345")
    graph = FakeLimpeza()
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, pid)[:2] == ("falhou", "contato_alterado")


def test_apagar_telefone_preserva_o_outro_telefone_do_contato(con):
    _ligar(con)
    _graph_linha(con, nome="Ana", original="12345", telefone=None, campo="home")
    _graph_linha(con, nome="Ana", original="+5511999990000", telefone="+5511999990000", campo="mobile")
    pid = _limpa(con, "apagar_telefone", "Ana", "Ana", "12345")
    g.aplicar(con, FakeLimpeza(), AGORA)
    assert _estado(con, pid)[0] == "aplicada" and _linhas_graph(con) == [("g-1", "Ana", "+5511999990000", "+5511999990000")]


def test_apagar_contato_tira_tambem_do_contato_google(con):
    pid, _ = _preparar(con, "apagar_contato")
    con.execute("insert into contato_google(conta, telefone, nome) values (?,?,?)", (NESS, "+5511947338256", "U"))
    con.commit()
    g.aplicar(con, FakeLimpeza(), AGORA)
    assert con.execute("select count(*) from contato_google").fetchone()[0] == 0


def test_tipo_desconhecido_vira_contato_alterado(con):
    _ligar(con)
    pid, _ = _preparar(con, "corrigir_nome")
    con.execute("pragma ignore_check_constraints=1")
    con.execute("update contato_proposta set tipo='inventado' where id=?", (pid,))
    con.commit()
    graph = FakeLimpeza()
    g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and _estado(con, pid)[:2] == ("falhou", "contato_alterado")


# ---------------- adicionar_email ----------------
class FakeEmail(FakeLimpeza):
    def contato_adicionar_email(self, conta, graph_id, nome_antes, telefone_antes, emails):
        return self._responde("adicionar_email", conta, graph_id, nome_antes, telefone_antes, emails)


E164 = "+5511912345678"


def _email(con, estado="aprovada", nome="Beltrano", emails="a@x.com;b@x.com", gid="g-1"):
    cur = con.execute("insert into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, email_depois, origem, estado) "
                      "values ('adicionar_email',?,?,?,?,?,?,?,'google_email',?)", (NESS, gid, nome, E164, nome, E164, emails, estado))
    con.commit()
    return cur.lastrowid


def _preparar_email(con, original="11 91234-5678 "):
    _ligar(con)
    _graph_linha(con, nome="Beltrano", original=original, telefone=E164)
    return _email(con)


def test_adicionar_email_ok_vira_aplicada_e_chama_a_ponte_com_original(con):
    pid = _preparar_email(con)
    graph = FakeEmail()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [("adicionar_email", NESS, "g-1", "Beltrano", "11 91234-5678 ", ["a@x.com", "b@x.com"])]
    assert r["aplicadas"] == 1 and _estado(con, pid)[0] == "aplicada"
    assert _linhas_graph(con) == [("g-1", "Beltrano", "11 91234-5678 ", E164)]


@pytest.mark.parametrize("quebra", ["nome", "sumiu", "conta_fora", "telefone", "duas_linhas"])
def test_adicionar_email_revalida_espelho(con, quebra):
    pid = _preparar_email(con)
    if quebra == "nome":
        con.execute("update contato_graph set nome='Mudou'")
    elif quebra == "sumiu":
        con.execute("delete from contato_graph")
    elif quebra == "telefone":
        con.execute("update contato_graph set telefone='+5511900000000'")
    elif quebra == "duas_linhas":
        _graph_linha(con, nome="Beltrano", original="outro", telefone=E164)
    con.commit()
    if quebra == "conta_fora":
        _contas(con, ["outra@x.com"])
    graph = FakeEmail()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and r["descartadas"] == 1 and _estado(con, pid)[:2] == ("falhou", "contato_alterado")


def test_adicionar_email_alterado_pelo_graph(con):
    pid = _preparar_email(con)
    r = g.aplicar(con, FakeEmail("alterado"), AGORA)
    assert _estado(con, pid)[:2] == ("falhou", "contato_alterado") and r["descartadas"] == 1


def test_adicionar_email_graph_cai(con):
    pid = _preparar_email(con)
    r = g.aplicar(con, FakeEmail(erro=True), AGORA)
    assert _estado(con, pid)[:2] == ("falhou", "graph_indisponivel") and r["descartadas"] == 0


def test_adicionar_email_desligado_nao_chama_o_graph(con):
    pid = _preparar_email(con)
    _ligar(con, "desligado")
    graph = FakeEmail()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and r["simuladas"] == 1 and _estado(con, pid)[0] == "aprovada"


@pytest.mark.parametrize("email_primeiro", [True, False])
def test_adicionar_email_com_corrigir_do_mesmo_contato_nao_quebra_em_nenhuma_ordem(con, email_primeiro):
    _ligar(con)
    _graph_linha(con, nome="Beltrano", original="11 91234-5678 ", telefone=E164)
    if email_primeiro:
        pe = _email(con)
        pc = _proposta(con, tipo="corrigir", nome="Beltrano", tel=E164, graph_id="g-1", nome_antes="Beltrano", tel_antes="11 91234-5678 ")
    else:
        pc = _proposta(con, tipo="corrigir", nome="Beltrano", tel=E164, graph_id="g-1", nome_antes="Beltrano", tel_antes="11 91234-5678 ")
        pe = _email(con)
    graph = FakeEmail()
    r = g.aplicar(con, graph, AGORA)
    assert r["aplicadas"] == 2 and _estado(con, pe)[0] == "aplicada" and _estado(con, pc)[0] == "aplicada"
    original_na_hora = "11 91234-5678 " if email_primeiro else E164
    assert [c for c in graph.chamadas if c[0] == "adicionar_email"] == [("adicionar_email", NESS, "g-1", "Beltrano", original_na_hora, ["a@x.com", "b@x.com"])]


def test_apagar_contato_preserva_contato_google_de_outro_contato_com_o_mesmo_telefone(con):
    pid, _ = _preparar(con, "apagar_contato")
    _graph_linha(con, graph_id="g-2", nome="Outro", original="+55 11 94733-8256", telefone="+5511947338256")
    con.execute("insert into contato_google(conta, telefone, nome) values (?,?,?)", (NESS, "+5511947338256", "U"))
    con.commit()
    g.aplicar(con, FakeLimpeza(), AGORA)
    assert _estado(con, pid)[0] == "aplicada"
    assert con.execute("select count(*) from contato_google").fetchone()[0] == 1


def test_recusar_durante_a_gravacao_nao_desfaz_o_apagar(con):
    from gabi.escuta import contatos_propostas as cp
    pid, _ = _preparar(con, "apagar_contato")
    resultado = {}

    class Corrida(FakeLimpeza):
        def contato_apagar(self, *a):
            try:
                cp.decidir(con, pid, "recusada", "ricardo", AGORA)
            except cp.ErroProposta as e:
                resultado["conflito"] = e.conflito
            return super().contato_apagar(*a)

    g.aplicar(con, Corrida(), AGORA)
    assert resultado == {"conflito": True} and _estado(con, pid)[0] == "aplicada"


def test_proposta_recusada_antes_de_comecar_nao_chama_o_graph(con):
    pid, _ = _preparar(con, "apagar_contato")
    con.execute("update contato_proposta set estado='recusada' where id=?", (pid,))
    con.commit()
    graph = FakeLimpeza()
    r = g.aplicar(con, graph, AGORA)
    assert graph.chamadas == [] and r["aplicadas"] == 0


def test_erro_do_banco_ao_reservar_nao_chama_o_graph(con):
    _ligar(con)
    a = _proposta(con, nome="A", tel="+5511911111111")
    graph = FakeGraph(ids=["id-a"])
    r = g.aplicar(_ConProxy(con, "update contato_proposta set motivo", vezes=1, so_id=a), graph, AGORA)
    assert graph.chamadas == [] and r["falhas"] == 1
