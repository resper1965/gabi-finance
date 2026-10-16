from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.decisoes import responder
from gabi.dinheiro.sugestoes_dono import MAX_ABERTAS, propor

MIGR = Path(__file__).parent.parent.parent / "migrations"
T = "2026-10-16T12:00:00+00:00"
_n = iter(range(1, 100000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','Itau','CREDIT','Cartão','sim')")      # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Outro','CREDIT','Outro','a_decidir')")  # 2
    for pid, nome in [("ricardo", "Ricardo"), ("pets", "Pets"), ("casa", "Casa (todos)")]:
        c.execute("insert into pessoa(id, nome) values (?,?)", (pid, nome))
    return c


def lanc(con, fornecedor, valor=10000, dono=None, conta=1, natureza="caixa+custo"):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, status, para_quem_id, para_quem_origem) "
                "values (?,?,'2026-10-10',?,?,?,?,'posted',?,?)", (conta, f"x{next(_n)}", -valor, fornecedor, fornecedor, natureza, dono, "banco" if dono else None))


def historico(con):
    for _ in range(5):
        lanc(con, "MERCADO", dono="casa")
    for _ in range(3):
        lanc(con, "RACAO", dono="pets")
    lanc(con, "BARBEIRO", dono="ricardo")


def test_fornecedor_com_dois_gastos_sem_dono_vira_pergunta_com_as_pessoas_mais_usadas(con):
    historico(con)
    lanc(con, "PETZ", 30000); lanc(con, "PETZ", 20000)
    assert propor(con, T) == 1
    p = con.execute("select titulo, contexto, opcoes from pergunta").fetchone()
    assert p["titulo"] == "De quem é o gasto em 'PETZ'?" and "2 lançamentos, R$ 500,00" in p["contexto"]
    import json
    rot = [o["rotulo"] for o in json.loads(p["opcoes"])]
    assert rot == ["Casa (todos)", "Pets", "Ricardo", "Deixar para depois"]  # ordem por uso; nada chumbado


def test_gasto_unico_conta_nao_liberada_e_nao_custo_ficam_de_fora(con):
    historico(con)
    lanc(con, "SO UMA VEZ")
    lanc(con, "OUTRA CONTA", conta=2); lanc(con, "OUTRA CONTA", conta=2)
    lanc(con, "TRANSFERENCIA", natureza="caixa"); lanc(con, "TRANSFERENCIA", natureza="caixa")
    assert propor(con, T) == 0


def test_no_maximo_cinco_abertas_e_nao_repete_pergunta(con):
    historico(con)
    for i in range(8):
        lanc(con, f"FORN{i}"); lanc(con, f"FORN{i}")
    assert propor(con, T) == MAX_ABERTAS and propor(con, T) == 0
    pid = con.execute("select id from pergunta order by id limit 1").fetchone()[0]
    responder(con, pid, 4, "ricardo", T)  # deixar para depois (3 pessoas + a opção 4): fecha a pergunta sem atribuir
    assert propor(con, T) == 1  # abriu vaga: pergunta a próxima, sem repetir a respondida
    assert con.execute("select count(distinct titulo) from pergunta").fetchone()[0] == 6


def test_resposta_preenche_so_o_que_esta_sem_dono_com_origem_voce(con):
    historico(con)
    lanc(con, "PETZ"); lanc(con, "PETZ"); lanc(con, "PETZ", dono="ricardo")
    propor(con, T)
    pid, = con.execute("select id from pergunta").fetchone()
    responder(con, pid, 2, "ricardo", T)  # Pets
    r = con.execute("select para_quem_id, para_quem_origem from lancamento where estabelecimento='PETZ' order by id").fetchall()
    assert [tuple(x) for x in r] == [("pets", "voce"), ("pets", "voce"), ("ricardo", "banco")]  # o já escolhido não é trocado


def test_sem_historico_de_pessoas_nao_pergunta(con):
    lanc(con, "PETZ"); lanc(con, "PETZ")
    assert propor(con, T) == 0
