import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.favorecidos import sugerir_por_favorecido

MIGR = Path(__file__).parent.parent.parent / "migrations"
_n = iter(range(1, 100000))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','BANK','sim')")
    c.execute("insert into categoria(nome) values ('Pessoal')")      # 1
    c.execute("insert into categoria(nome) values ('Serviços')")     # 2
    return c


def pix(con, nome, cat=None, n=1):
    for _ in range(n):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_id, status) values (1,?,?,?,?,?, 'posted')",
                    (f"p{next(_n)}", "2026-09-10", -10000, f"Pix enviado {nome}", cat))


def pendentes(con):
    return [json.loads(r["payload"]) for r in con.execute("select payload from sugestao where tipo='regra' and estado='pendente'")]


def test_sugere_quando_favorecido_repete_com_categoria_unica(con):
    pix(con, "SIRLENE ARAUJO SANTOS", cat=2, n=2)   # irmãos categorizados
    pix(con, "SIRLENE ARAUJO SANTOS", n=3)          # os que faltam
    assert sugerir_por_favorecido(con) == 1
    p = pendentes(con)[0]
    assert p["acao"] == {"categoria_id": 2} and "SIRLENE" in p["padrao"]


def test_sem_irmaos_categorizados_a_sugestao_vem_sem_categoria_para_o_ricardo_escolher(con):
    pix(con, "BEKAA TECNOLOGIA LTDA", n=4)
    assert sugerir_por_favorecido(con) == 1
    assert pendentes(con)[0]["acao"] == {"categoria_id": None}


def test_nao_sugere_se_categorias_dos_irmaos_divergem(con):
    pix(con, "THIAGO X", cat=1); pix(con, "THIAGO X", cat=2); pix(con, "THIAGO X", n=3)
    assert sugerir_por_favorecido(con) == 0


def test_nao_duplica_sugestao_pendente(con):
    pix(con, "CARLA NOCE", n=3)
    assert sugerir_por_favorecido(con) == 1 and sugerir_por_favorecido(con) == 0
    assert len(pendentes(con)) == 1


def test_nao_sugere_para_favorecido_com_menos_de_minimo(con):
    pix(con, "ROSEANE PEREIRA", n=2)
    assert sugerir_por_favorecido(con, minimo=3) == 0 and sugerir_por_favorecido(con, minimo=2) == 1


def test_favorecido_ja_coberto_por_regra_ativa_de_categoria_nao_gera_sugestao(con):
    pix(con, "MARIANA TOLEDO", n=3)
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('MARIANA TOLEDO', ?, 1, 'x', 'r')", (json.dumps({"categoria_id": 1}),))
    assert sugerir_por_favorecido(con) == 0


def test_so_pix_enviado_entra_e_o_nome_com_numeros_ou_espacos_e_normalizado(con):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (1,'x1','2026-09-01',-100,'Pagamento de boleto X','posted')")
    pix(con, "ANA   LIMA", n=2); pix(con, "ana lima", n=1)
    assert sugerir_por_favorecido(con) == 1 and len(pendentes(con)) == 1


def test_sugestao_rejeitada_nao_volta_na_rodada_seguinte(con):
    pix(con, "CARLA NOCE", n=3)
    assert sugerir_por_favorecido(con) == 1
    con.execute("update sugestao set estado='rejeitada'")
    assert sugerir_por_favorecido(con) == 0
    assert con.execute("select count(*) from sugestao where estado='pendente'").fetchone()[0] == 0
