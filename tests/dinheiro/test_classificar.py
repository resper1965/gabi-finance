import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.classificar import Classificacao, classificar, classificar_pendentes

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','C6','BANK','sim')")
    for n in ("Mercado", "Transporte", "Restaurante"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    c.execute("insert into pessoa(id, nome) values ('p2','Bia')")
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    return c


def _lanc(con, i, desc="UBER TRIP", estab=None, cat_banco=None, **extra):
    cols = {"conta_id": 1, "externo_id": f"l{i}", "data": "2026-10-08", "valor_centavos": -1000, "descricao_original": desc,
            "estabelecimento": estab if estab is not None else desc.split()[0], "categoria_banco": cat_banco, **extra}
    con.execute(f"insert into lancamento({','.join(cols)}) values ({','.join('?' * len(cols))})", list(cols.values()))
    return con.execute("select id from lancamento where externo_id=?", (f"l{i}",)).fetchone()[0]


def _regra(con, padrao, acao, ativa=1):
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values (?,?,?, '2026-10-08', 'voce')",
                (padrao, json.dumps(acao), ativa))


def _l(con, lid):
    return con.execute("select * from lancamento where id=?", (lid,)).fetchone()


def test_regra_ativa_aplica_com_origem_regra(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1"})
    lid = _lanc(con, 1)
    c = classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"], r["para_quem_id"], r["para_quem_origem"]) == (2, "regra", "p1", "regra")
    assert isinstance(c, Classificacao) and c.categoria_id == 2 and c.origens["categoria"] == "regra" and c.confianca == 1.0


def test_regra_inativa_nao_aplica(con):
    _regra(con, "UBER", {"categoria_id": 2}, ativa=0)  # R1: só vale depois do Ricardo ligar
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] is None


def test_regra_ganha_da_equivalencia_do_banco(con):
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Transport', 3)")
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1, cat_banco="Transport")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"]) == (2, "regra")


def test_equivalencia_do_banco_aplica_com_origem_banco(con):
    con.execute("insert into equivalencia_categoria(origem_pluggy, categoria_id) values ('Groceries', 1)")
    lid = _lanc(con, 1, "PADARIA", cat_banco="Groceries")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"]) == (1, "banco")


def test_decisao_do_ricardo_nunca_e_sobrescrita(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1", "empresa_id": "e1"})
    lid = _lanc(con, 1, categoria_id=3, categoria_origem="voce", para_quem_id="p2", para_quem_origem="voce")
    classificar(con, lid)
    r = _l(con, lid)
    assert (r["categoria_id"], r["categoria_origem"], r["para_quem_id"], r["para_quem_origem"]) == (3, "voce", "p2", "voce")
    assert (r["empresa_id"], r["empresa_origem"]) == ("e1", "regra")  # o campo livre é preenchido


def test_regra_so_com_um_campo_deixa_os_outros_em_branco(con):
    _regra(con, "UBER", {"para_quem_id": "p1"})
    lid = _lanc(con, 1)
    classificar(con, lid)
    r = _l(con, lid)
    assert r["para_quem_id"] == "p1" and r["categoria_id"] is None and r["empresa_id"] is None


def test_regra_com_regex_invalido_e_ignorada_sem_quebrar(con):
    _regra(con, "([", {"categoria_id": 1})
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_regra_com_acao_invalida_e_ignorada(con):
    con.execute("insert into regra(padrao, acao, ativa, criado_em) values ('UBER','isto nao e json',1,'2026-10-08')")
    _regra(con, "UBER", {"categoria_id": 2})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_primeira_regra_por_id_vence(con):
    _regra(con, "UBER", {"categoria_id": 2})
    _regra(con, "UBER", {"categoria_id": 3})
    lid = _lanc(con, 1)
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2


def test_cache_por_estabelecimento_so_sugere_nao_grava(con):
    _lanc(con, 1, "PADARIA BOM PAO", estab="PADARIA BOM PAO", categoria_id=1, categoria_origem="voce")
    novo = _lanc(con, 2, "PADARIA BOM PAO LTDA", estab="PADARIA BOM PAO")
    classificar(con, novo)
    assert _l(con, novo)["categoria_id"] is None  # R1: uma decisão sua vale só para aquele lançamento
    s = con.execute("select * from sugestao").fetchall()
    assert len(s) == 1 and s[0]["tipo"] == "categoria" and s[0]["estado"] == "pendente" and s[0]["lancamento_id"] == novo
    assert json.loads(s[0]["payload"])["categoria_id"] == 1


def test_cache_nao_duplica_sugestao_pendente(con):
    _lanc(con, 1, "PADARIA", estab="PADARIA", categoria_id=1, categoria_origem="voce")
    novo = _lanc(con, 2, "PADARIA", estab="PADARIA")
    classificar(con, novo)
    classificar(con, novo)
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 1


def test_cache_com_decisoes_divergentes_nao_sugere(con):
    _lanc(con, 1, "PADARIA", estab="PADARIA", categoria_id=1, categoria_origem="voce")
    _lanc(con, 2, "PADARIA", estab="PADARIA", categoria_id=3, categoria_origem="voce")
    novo = _lanc(con, 3, "PADARIA", estab="PADARIA")
    classificar(con, novo)
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 0


def test_sem_resolucao_nao_grava_nada_nem_quebra(con):
    lid = _lanc(con, 1, "COISA NUNCA VISTA")
    c = classificar(con, lid)
    r = _l(con, lid)
    assert r["categoria_id"] is None and r["para_quem_id"] is None and c.confianca == 0.0 and c.origens == {}
    assert con.execute("select count(*) from sugestao").fetchone()[0] == 0


def test_classificar_pendentes_percorre_so_o_que_falta(con):
    _regra(con, "UBER", {"categoria_id": 2, "para_quem_id": "p1"})
    a = _lanc(con, 1)
    _lanc(con, 2, "X", categoria_id=1, categoria_origem="voce", para_quem_id="p1", para_quem_origem="voce")
    b = _lanc(con, 3, "OUTRA COISA")
    r = classificar_pendentes(con)
    assert r.examinados == 2 and r.resolvidos == 1
    assert _l(con, a)["categoria_id"] == 2 and _l(con, b)["categoria_id"] is None


def test_lancamento_inexistente_levanta_LookupError(con):
    with pytest.raises(LookupError):
        classificar(con, 9999)


def test_regra_tambem_casa_pelo_estabelecimento_normalizado(con):
    _regra(con, "^LOJA X$", {"categoria_id": 2})
    lid = _lanc(con, 1, desc="LOJA (X) *123", estab="LOJA X")  # a descrição original tem pontuação; o estabelecimento é normalizado
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] == 2
