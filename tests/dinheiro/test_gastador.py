import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import gastador

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    for pid, nome, papel in [("ricardo", "Ricardo", "titular"), ("louise", "Louise", "filha"), ("sabrina", "Sabrina", "esposa"), ("carla", "Carla", "ex-esposa")]:
        c.execute("insert into pessoa(id, nome, papel) values (?,?,?)", (pid, nome, papel))
    for cid, tipo, apelido, usuarios in [(1, "BANK", "itau", None), (2, "CREDIT", "Pao de Acucar", ["sabrina"]),
                                         (3, "CREDIT", "LATAM", ["ricardo", "louise"]), (4, "CREDIT", "Platinum", None),
                                         (5, "CREDIT", "MC Black", ["ricardo", "louise"])]:
        c.execute("insert into conta(id, externo_id, instituicao, tipo, apelido, estado, usuarios) values (?,?,?,?,?, 'sim', ?)",
                  (cid, f"x{cid}", "Itaú", tipo, apelido, json.dumps(usuarios) if usuarios else None))
    return c


def lanc(con, conta, estab="LOJA", valor=-1000, natureza=None):
    nat = natureza or ("custo" if conta != 1 else "caixa+custo")
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, status) "
                       "values (?,?, '2026-10-10', ?,?,?,?, 'posted')", (conta, f"e{conta}{estab}{valor}{natureza}", valor, estab, estab, nat)).lastrowid


def g(con, lid):
    return tuple(con.execute("select gastador_id, gastador_origem from lancamento where id=?", (lid,)).fetchone())


def test_um_portador_vem_do_cartao(con):
    lid = lanc(con, 2)
    gastador.preencher(con)
    assert g(con, lid) == ("sabrina", "cartao")


def test_compartilhado_fica_a_indicar(con):
    lid, sem = lanc(con, 3), lanc(con, 4)
    r = gastador.preencher(con)
    assert g(con, lid) == (None, None) and g(con, sem) == (None, None)
    assert r["a_indicar"] == 2


def test_conta_corrente_e_do_titular(con):
    lid = lanc(con, 1)
    gastador.preencher(con)
    assert g(con, lid) == ("ricardo", "cartao")


def test_indicacao_do_ricardo_nao_e_sobrescrita(con):
    lid = lanc(con, 3)
    gastador.indicar(con, [lid], "louise")
    gastador.preencher(con)
    assert g(con, lid) == ("louise", "voce")
    gastador.indicar(con, [lid], None)  # tirar a indicação: volta ao automático
    assert g(con, lid) == (None, None)


def test_um_para_dois_portadores_volta_a_indicar(con):
    lid = lanc(con, 4)
    con.execute("update conta set usuarios='[\"ricardo\"]' where id=4")
    gastador.preencher(con)
    assert g(con, lid) == ("ricardo", "cartao")
    con.execute("update conta set usuarios='[\"ricardo\",\"louise\"]' where id=4")
    gastador.preencher(con)
    assert g(con, lid) == (None, None)


def test_tirar_portador_mantem_indicacao_voce(con):
    lid = lanc(con, 3)
    gastador.indicar(con, [lid], "louise")
    con.execute("update conta set usuarios='[\"ricardo\"]' where id=3")
    gastador.preencher(con)
    assert g(con, lid) == ("louise", "voce")


def test_regra_da_loja_so_no_mesmo_cartao(con):
    a, b, outro_cartao = lanc(con, 3, "ZARA"), lanc(con, 3, "ZARA", -2000), lanc(con, 5, "ZARA")
    gastador.indicar(con, [a], "louise", regra=True)
    assert g(con, a) == ("louise", "voce") and g(con, b) == ("louise", "regra")
    assert g(con, outro_cartao) == (None, None)
    novo = lanc(con, 3, "ZARA", -3000)
    gastador.preencher(con, [novo])
    assert g(con, novo) == ("louise", "regra")
    gastador.indicar(con, [a], "ricardo", regra=True)  # regra trocada: os 'regra' acompanham
    assert g(con, b) == ("ricardo", "regra") and g(con, novo) == ("ricardo", "regra")


def test_indicar_nao_portador_recusa_e_nao_grava_nada(con):
    a, b = lanc(con, 3), lanc(con, 2)
    with pytest.raises(ValueError, match="nao_portador"):
        gastador.indicar(con, [a, b], "louise")  # louise não é portadora do Pão de Açúcar
    assert g(con, a) == (None, None)
    with pytest.raises(ValueError, match="nao_portador"):
        gastador.indicar(con, [a], "carla")
    with pytest.raises(LookupError):
        gastador.indicar(con, [999], "louise")


def test_portadores(con):
    assert gastador.portadores(con, 3) == ["ricardo", "louise"]
    assert gastador.portadores(con, 4) == []
    assert gastador.portadores(con, 1) == ["ricardo"]  # conta corrente sem usuário: o titular
