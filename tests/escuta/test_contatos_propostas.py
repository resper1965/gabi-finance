from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta import contatos as c
from gabi.escuta import contatos_propostas as p

MIGR = Path(__file__).parent.parent.parent / "migrations"
NESS = "resper@ness.com.br"
AGORA = "2026-10-20T10:00:00Z"
NUM = "+5511912345678"


@pytest.fixture
def con(tmp_path):
    k = conectar(tmp_path / "t.db")
    migrar(k, MIGR)
    return k


def _rem(con, numero=NUM, nome="Fulano", estado="aprovado"):
    con.execute("insert into escuta_remetente(numero, nome, estado) values (?,?,?)", (numero, nome, estado))


def _graph(con, gid="g1", nome="Beltrano", orig="11 9999-0000", tel=None, campo="mobile", conta=NESS):
    con.execute("insert into contato_graph(conta, graph_id, nome, telefone_original, telefone, campo) values (?,?,?,?,?,?)",
                (conta, gid, nome, orig, tel, campo))


def _props(con):
    return [dict(r) for r in con.execute("select * from contato_proposta order by id")]


def test_criar_para_remetente_aprovado_com_nome_sem_contato(con):
    _rem(con, nome="  Fulano  ")
    assert p.gerar(con, AGORA) == {"criar": 1, "corrigir": 0}
    (r,) = _props(con)
    assert (r["tipo"], r["conta"], r["graph_id"], r["origem"], r["estado"]) == ("criar", NESS, None, "whatsapp", "pendente")
    assert (r["nome_depois"], r["telefone_depois"], r["criada_em"]) == ("Fulano", NUM, AGORA)


@pytest.mark.parametrize("nome", [None, "", "   "])
def test_nao_cria_sem_nome(con, nome):
    _rem(con, nome=nome)
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}


def test_nao_cria_remetente_nao_aprovado_ou_numero_estranho(con):
    _rem(con, estado="pendente")
    _rem(con, numero="123", nome="X")
    assert p.gerar(con, AGORA)["criar"] == 0


@pytest.mark.parametrize("onde", ["graph", "google"])
def test_nao_cria_se_numero_ja_e_contato_ness_ou_google(con, onde):
    _rem(con)
    if onde == "graph":
        _graph(con, orig="x", tel=NUM, conta="outra@x.com")
    else:
        con.execute("insert into contato_google(conta, telefone, nome) values ('resper@gmail.com',?,'G')", (NUM,))
    assert p.gerar(con, AGORA)["criar"] == 0


def test_corrigir_quando_original_invalido_vira_valido(con):
    _graph(con)
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 1}
    (r,) = _props(con)
    assert (r["tipo"], r["graph_id"], r["origem"]) == ("corrigir", "g1", "telefone_invalido")
    assert (r["nome_antes"], r["telefone_antes"], r["nome_depois"]) == ("Beltrano", "11 9999-0000", "Beltrano")
    assert r["telefone_depois"] == c._telefone({"telefone": "11 9999-0000"})


def test_nao_corrige_se_a_regra_nao_produz_numero(con):
    _graph(con, orig="(11) 3333-4444 ramal 5")
    assert p.gerar(con, AGORA)["corrigir"] == 0


@pytest.mark.parametrize("nome", [None, "  "])
def test_nao_corrige_contato_sem_nome(con, nome):
    _graph(con, nome=nome)
    assert p.gerar(con, AGORA)["corrigir"] == 0


@pytest.mark.parametrize("campo", ["home", "business", None])
def test_nao_corrige_telefone_fixo_ou_de_trabalho(con, campo):
    _graph(con, campo=campo)
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_nao_corrige_se_contato_ja_tem_o_mesmo_numero(con):
    _graph(con)
    _graph(con, orig="+5511999990000", tel="+5511999990000", campo="home")
    assert p.gerar(con, AGORA)["corrigir"] == 0


def test_recusada_nao_repete_mesmo_valor_e_repete_valor_novo(con):
    _graph(con)
    p.gerar(con, AGORA)
    p.decidir(con, _props(con)[0]["id"], "recusada", "ricardo", AGORA)
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}
    con.execute("update contato_graph set nome='Novo Nome'")
    assert p.gerar(con, AGORA)["corrigir"] == 1
    assert len(_props(con)) == 2


def test_aplicada_nao_repete(con):
    _rem(con)
    p.gerar(con, AGORA)
    con.execute("update contato_proposta set estado='aplicada'")
    assert p.gerar(con, AGORA)["criar"] == 0


def test_gerar_e_idempotente(con):
    _rem(con)
    _graph(con)
    assert p.gerar(con, AGORA) == {"criar": 1, "corrigir": 1}
    assert p.gerar(con, AGORA) == {"criar": 0, "corrigir": 0}
    assert len(_props(con)) == 2


def test_decidir_so_de_pendente(con):
    _rem(con)
    p.gerar(con, AGORA)
    pid = _props(con)[0]["id"]
    p.decidir(con, pid, "aprovada", "ricardo", AGORA)
    r = _props(con)[0]
    assert (r["estado"], r["decidida_por"], r["decidida_em"]) == ("aprovada", "ricardo", AGORA)
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, pid, "recusada", "ricardo", AGORA)
    assert e.value.conflito
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, 999, "aprovada", "ricardo", AGORA)
    assert e.value.nao_encontrado
    with pytest.raises(p.ErroProposta) as e:
        p.decidir(con, pid, "aplicada", "ricardo", AGORA)
    assert not e.value.conflito and not e.value.nao_encontrado


def test_aprovar_correcoes_so_do_tipo_corrigir(con):
    _rem(con)
    _graph(con)
    p.gerar(con, AGORA)
    assert p.aprovar_correcoes(con, "ricardo", AGORA) == 1
    assert {r["tipo"]: r["estado"] for r in _props(con)} == {"criar": "pendente", "corrigir": "aprovada"}
    assert p.aprovar_correcoes(con, "ricardo", AGORA) == 0


def test_listar_filtra_por_estado_e_ordena(con):
    _rem(con)
    _graph(con)
    p.gerar(con, AGORA)
    assert [r["tipo"] for r in p.listar(con)] == ["criar", "corrigir"]
    p.aprovar_correcoes(con, "r", AGORA)
    assert [r["tipo"] for r in p.listar(con, "aprovada")] == ["corrigir"]


def test_main_gera_propostas_e_imprime_so_contagens(tmp_path, capsys):
    banco = tmp_path / "m.db"
    k = conectar(banco); migrar(k, MIGR); _rem(k, nome="Segredo"); k.commit(); k.close()
    code = c.main(banco, listar=lambda conta: [])
    out = capsys.readouterr().out
    assert code == 0 and "propostas: criar=1 corrigir=0" in out and "Segredo" not in out and "912345678" not in out
