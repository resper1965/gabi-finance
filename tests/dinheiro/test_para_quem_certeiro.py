import json

import pytest

from gabi.dinheiro.classificar import MIN_DECISOES_CERTEIRO, classificar
from gabi.dinheiro.para_quem_fila import aplicar_fila_para_quem
from tests.dinheiro.test_classificar import _l, _lanc, con  # noqa: F401  (fixture con)

AGORA = "2026-10-22T10:00:00+00:00"


def _decidido(con, i, estab, pessoa):
    return _lanc(con, i, desc=f"{estab} X", estab=estab, para_quem_id=pessoa, para_quem_origem="voce")


def _pendentes(con, lid, tipo="para_quem"):
    return con.execute("select count(*) from sugestao where lancamento_id=? and tipo=? and estado='pendente'", (lid, tipo)).fetchone()[0]


def test_minimo_e_duas_decisoes():
    assert MIN_DECISOES_CERTEIRO == 2


def test_aplica_com_duas_decisoes_iguais(con):
    _decidido(con, 1, "ESPACOLASER", "p1")
    _decidido(con, 2, "ESPACOLASER", "p1")
    lid = _lanc(con, 3, desc="ESPACOLASER X", estab="ESPACOLASER")
    c = classificar(con, lid)
    r = _l(con, lid)
    assert (r["para_quem_id"], r["para_quem_origem"]) == ("p1", "gabi") and c.origens["para_quem"] == "gabi"
    assert _pendentes(con, lid) == 0
    d = con.execute("select quem, origem, o_que from decisao").fetchall()
    assert len(d) == 1 and (d[0]["quem"], d[0]["origem"]) == ("gabi (para quem certeiro)", "classificacao") and f"lançamento {lid}" in d[0]["o_que"]


def test_sugere_com_uma_decisao(con):
    _decidido(con, 1, "PETZ", "p1")
    lid = _lanc(con, 2, desc="PETZ X", estab="PETZ")
    classificar(con, lid)
    assert _l(con, lid)["para_quem_id"] is None and _pendentes(con, lid) == 1
    assert con.execute("select count(*) from decisao").fetchone()[0] == 0


def test_nao_aplica_se_decisoes_divergem(con):
    _decidido(con, 1, "VIVO", "p1")
    _decidido(con, 2, "VIVO", "p1")
    _decidido(con, 3, "VIVO", "p2")
    lid = _lanc(con, 4, desc="VIVO X", estab="VIVO")
    classificar(con, lid)
    assert _l(con, lid)["para_quem_id"] is None and _pendentes(con, lid) == 0


@pytest.mark.parametrize("origem", ["voce", "regra", "fonte"])
def test_nao_sobrescreve(con, origem):
    _decidido(con, 1, "CLARO", "p1")
    _decidido(con, 2, "CLARO", "p1")
    lid = _lanc(con, 3, desc="CLARO X", estab="CLARO", para_quem_id="p2", para_quem_origem=origem)
    classificar(con, lid)
    assert (_l(con, lid)["para_quem_id"], _l(con, lid)["para_quem_origem"]) == ("p2", origem)
    assert con.execute("select count(*) from decisao").fetchone()[0] == 0


def test_categoria_continua_sugestao(con):
    for i in (1, 2):
        _lanc(con, i, desc="MERCADAO X", estab="MERCADAO", categoria_id=1, categoria_origem="voce")
    lid = _lanc(con, 3, desc="MERCADAO X", estab="MERCADAO")
    classificar(con, lid)
    assert _l(con, lid)["categoria_id"] is None and _pendentes(con, lid, "categoria") == 1


def test_fila_aplica_pendentes(con):
    _decidido(con, 1, "SEGURO", "p1")
    certa = _lanc(con, 2, desc="SEGURO X", estab="SEGURO")
    so_uma = _lanc(con, 3, desc="NETFLIX X", estab="NETFLIX")
    _decidido(con, 4, "NETFLIX", "p2")
    for lid, pessoa in ((certa, "p1"), (so_uma, "p2")):
        con.execute("insert into sugestao(tipo, lancamento_id, payload, motivo, criado_em) values ('para_quem',?,?,?, '2026-10-21')",
                    (lid, json.dumps({"para_quem_id": pessoa}), "você classificou assim os outros lançamentos"))
    _decidido(con, 5, "SEGURO", "p1")  # a segunda decisão chega depois da sugestão: agora é certeiro
    assert aplicar_fila_para_quem(con, AGORA) == 1
    assert (_l(con, certa)["para_quem_id"], _l(con, certa)["para_quem_origem"]) == ("p1", "gabi")
    s = con.execute("select estado, motivo, decidida_em from sugestao where lancamento_id=?", (certa,)).fetchone()
    assert s["estado"] == "aprovada" and s["motivo"].endswith("aplicada sozinha") and s["decidida_em"] == AGORA
    assert con.execute("select estado from sugestao where lancamento_id=?", (so_uma,)).fetchone()[0] == "pendente"
    assert _l(con, so_uma)["para_quem_id"] is None
    assert aplicar_fila_para_quem(con, AGORA) == 0


def test_fila_nao_aplica_se_o_lancamento_ja_tem_dono(con):
    _decidido(con, 1, "SEGURO", "p1")
    _decidido(con, 2, "SEGURO", "p1")
    lid = _lanc(con, 3, desc="SEGURO X", estab="SEGURO", para_quem_id="p2", para_quem_origem="voce")
    con.execute("insert into sugestao(tipo, lancamento_id, payload, motivo, criado_em) values ('para_quem',?,?, 'x', '2026-10-21')",
                (lid, json.dumps({"para_quem_id": "p1"})))
    assert aplicar_fila_para_quem(con, AGORA) == 0 and _l(con, lid)["para_quem_id"] == "p2"


def test_certeiro_fecha_a_sugestao_pendente_do_lancamento_na_rodada_real(con):
    """classificar_pendentes roda antes da fila: aplicar o certeiro precisa fechar a sugestão antiga, senão ela fica pendente para sempre."""
    from gabi.dinheiro.classificar import classificar_pendentes
    _decidido(con, 1, "SEGURO", "p1")
    lid = _lanc(con, 2, desc="SEGURO X", estab="SEGURO")
    classificar(con, lid)
    assert _pendentes(con, lid) == 1                     # 1 decisão: só sugere
    _decidido(con, 3, "SEGURO", "p1")                    # a 2ª decisão chega
    classificar_pendentes(con)
    aplicar_fila_para_quem(con, AGORA)
    assert (_l(con, lid)["para_quem_id"], _l(con, lid)["para_quem_origem"]) == ("p1", "gabi")
    assert _pendentes(con, lid) == 0
    s = con.execute("select estado, motivo from sugestao where lancamento_id=? and tipo='para_quem'", (lid,)).fetchone()
    assert s["estado"] == "aprovada" and s["motivo"].endswith("aplicada sozinha")


def test_fila_fecha_pendente_de_lancamento_que_ja_tem_dono_gabi(con):
    _decidido(con, 1, "SEGURO", "p1")
    _decidido(con, 2, "SEGURO", "p1")
    lid = _lanc(con, 3, desc="SEGURO X", estab="SEGURO", para_quem_id="p1", para_quem_origem="gabi")
    con.execute("insert into sugestao(tipo, lancamento_id, payload, motivo, criado_em) values ('para_quem',?,?, 'x', '2026-10-21')",
                (lid, json.dumps({"para_quem_id": "p1"})))
    aplicar_fila_para_quem(con, AGORA)
    assert _pendentes(con, lid) == 0
