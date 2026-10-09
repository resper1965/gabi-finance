import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.regras import (aprovar, aprovar_lote, contar_afetados, criar_regra_ativa, criar_sugestao, definir_ativa, rejeitar, sempre_assim)

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 8)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','C6','BANK','sim')")
    for n in ("Mercado", "Transporte", "Restaurante"):
        c.execute("insert into categoria(nome) values (?)", (n,))
    c.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    c.execute("insert into empresa(id, nome) values ('e1','Ness')")
    return c


def _l(con, i, desc="UBER TRIP", estab="UBER", data="2026-09-10", **extra):
    cols = {"conta_id": 1, "externo_id": f"l{i}", "data": data, "valor_centavos": -1000, "descricao_original": desc, "estabelecimento": estab, **extra}
    con.execute(f"insert into lancamento({','.join(cols)}) values ({','.join('?' * len(cols))})", list(cols.values()))
    return con.execute("select id from lancamento where externo_id=?", (f"l{i}",)).fetchone()[0]


def _get(con, lid):
    return con.execute("select * from lancamento where id=?", (lid,)).fetchone()


def _sug_regra(con, padrao="UBER", acao=None):
    return criar_sugestao(con, "regra", None, {"padrao": padrao, "acao": acao if acao is not None else {"categoria_id": 2, "para_quem_id": "p1"}}, "Gabi sugere")


def test_criar_sugestao_nasce_pendente_e_nao_cria_regra(con):
    sid = _sug_regra(con)
    s = con.execute("select * from sugestao where id=?", (sid,)).fetchone()
    assert s["estado"] == "pendente" and s["tipo"] == "regra" and s["decidida_em"] is None
    assert con.execute("select count(*) from regra").fetchone()[0] == 0  # R1


def test_aprovar_cria_regra_ativa_e_aplica_ao_passado(con):
    a, b, c = _l(con, 1), _l(con, 2, "UBER EATS", "UBER"), _l(con, 3, "PADARIA", "PADARIA")
    rid = aprovar(con, _sug_regra(con), None, por="boss@x.com")
    r = con.execute("select * from regra where id=?", (rid,)).fetchone()
    assert r["ativa"] == 1 and r["criada_por"] == "boss@x.com" and json.loads(r["acao"]) == {"categoria_id": 2, "para_quem_id": "p1"}
    for lid in (a, b):
        x = _get(con, lid)
        assert (x["categoria_id"], x["categoria_origem"], x["para_quem_id"], x["para_quem_origem"]) == (2, "regra", "p1", "regra")
    assert _get(con, c)["categoria_id"] is None
    assert con.execute("select estado from sugestao").fetchone()[0] == "aprovada"
    d = con.execute("select quem, o_que from decisao order by id desc limit 1").fetchone()
    assert d["quem"] == "boss@x.com" and "regra" in d["o_que"]


def test_aprovar_nunca_sobrescreve_decisao_do_ricardo_nem_regra_anterior(con):
    voce = _l(con, 1, categoria_id=3, categoria_origem="voce")
    regra_antiga = _l(con, 2, "UBER X", "UBER", categoria_id=1, categoria_origem="regra")
    banco = _l(con, 3, "UBER Y", "UBER", categoria_id=1, categoria_origem="banco")
    aprovar(con, _sug_regra(con, acao={"categoria_id": 2}), None, por="x")
    assert _get(con, voce)["categoria_id"] == 3 and _get(con, regra_antiga)["categoria_id"] == 1
    assert (_get(con, banco)["categoria_id"], _get(con, banco)["categoria_origem"]) == (2, "regra")  # sugestão do banco pode ser trocada


def test_aprovar_com_edicao_usa_a_versao_editada(con):
    a = _l(con, 1)
    rid = aprovar(con, _sug_regra(con), {"acao": {"categoria_id": 3}}, por="x")
    assert json.loads(con.execute("select acao from regra where id=?", (rid,)).fetchone()[0]) == {"categoria_id": 3}
    assert _get(con, a)["categoria_id"] == 3 and _get(con, a)["para_quem_id"] is None


def test_rejeitar_nao_cria_regra_e_registra(con):
    sid = _sug_regra(con)
    rejeitar(con, sid, por="boss@x.com")
    assert con.execute("select estado from sugestao").fetchone()[0] == "rejeitada"
    assert con.execute("select count(*) from regra").fetchone()[0] == 0
    assert con.execute("select quem from decisao order by id desc limit 1").fetchone()[0] == "boss@x.com"


def test_sugestao_ja_decidida_nao_pode_ser_decidida_de_novo(con):
    sid = _sug_regra(con)
    aprovar(con, sid, None, por="x")
    with pytest.raises(ValueError):
        aprovar(con, sid, None, por="x")
    with pytest.raises(ValueError):
        rejeitar(con, sid, por="x")
    assert con.execute("select count(*) from regra").fetchone()[0] == 1


def test_sugestao_inexistente_levanta(con):
    with pytest.raises(LookupError):
        aprovar(con, 999, None, por="x")


@pytest.mark.parametrize("padrao,acao", [("([", {"categoria_id": 1}), ("UBER", {"categoria_id": 999}), ("UBER", {"para_quem_id": "fantasma"}),
                                          ("UBER", {"empresa_id": "fantasma"}), ("UBER", {}), ("UBER", {"coisa": 1}), ("", {"categoria_id": 1})])
def test_regra_invalida_e_recusada_e_nada_muda(con, padrao, acao):
    a = _l(con, 1)
    sid = _sug_regra(con, padrao, acao)
    with pytest.raises(ValueError):
        aprovar(con, sid, None, por="x")
    assert con.execute("select count(*) from regra").fetchone()[0] == 0
    assert con.execute("select estado from sugestao").fetchone()[0] == "pendente"
    assert _get(con, a)["categoria_id"] is None


def test_sugestao_de_um_lancamento_aprovada_grava_com_origem_voce(con):
    a = _l(con, 1)
    sid = criar_sugestao(con, "categoria", a, {"categoria_id": 2}, "você classificou assim os outros")
    assert aprovar(con, sid, None, por="x") is None  # não cria regra
    x = _get(con, a)
    assert (x["categoria_id"], x["categoria_origem"]) == (2, "voce")
    assert con.execute("select count(*) from regra").fetchone()[0] == 0


def test_sugestao_de_lancamento_nao_sobrescreve_campo_ja_decidido(con):
    a = _l(con, 1, categoria_id=3, categoria_origem="voce")
    sid = criar_sugestao(con, "categoria", a, {"categoria_id": 2}, "m")
    with pytest.raises(ValueError):
        aprovar(con, sid, None, por="x")
    assert _get(con, a)["categoria_id"] == 3


def test_contar_afetados_passado_e_futuro(con):
    for i in range(6):
        _l(con, i, data=f"2026-0{4 + i}-10" if 4 + i < 10 else "2026-09-10")
    _l(con, 10, "UBER Z", "UBER", data="2026-09-20", categoria_id=1, categoria_origem="voce")  # decidido por você: não muda
    _l(con, 11, "PADARIA", "PADARIA")
    r = contar_afetados(con, "UBER", {"categoria_id": 2}, HOJE)
    assert r["passado"] == 6 and r["futuro_estimado"] == 1.0  # afeta 6 (1 já é seu); nos últimos 180 dias casam 6 (o de 10/04 fica 1 dia fora): 6/6 = 1,0 por mês


def test_contar_afetados_regex_invalido_levanta(con):
    with pytest.raises(ValueError):
        contar_afetados(con, "([", {"categoria_id": 1}, HOJE)


def test_aprovar_lote_e_atomico(con):
    a = _sug_regra(con, "UBER")
    b = _sug_regra(con, "PADARIA", {"categoria_id": 1})
    ruim = _sug_regra(con, "([", {"categoria_id": 1})
    with pytest.raises(ValueError):
        aprovar_lote(con, [a, b, ruim], por="x")
    assert con.execute("select count(*) from regra").fetchone()[0] == 0
    assert {r[0] for r in con.execute("select estado from sugestao")} == {"pendente"}
    assert len(aprovar_lote(con, [a, b], por="x")) == 2 and con.execute("select count(*) from regra").fetchone()[0] == 2


def test_sempre_assim_cria_regra_ativa_com_o_que_voce_decidiu(con):
    a = _l(con, 1, "UBER TRIP", "UBER", categoria_id=2, categoria_origem="voce", para_quem_id="p1", para_quem_origem="voce")
    outro = _l(con, 2, "UBER EATS", "UBER")
    rid = sempre_assim(con, a, por="boss@x.com")
    r = con.execute("select * from regra where id=?", (rid,)).fetchone()
    assert r["ativa"] == 1 and json.loads(r["acao"]) == {"categoria_id": 2, "para_quem_id": "p1"} and r["criada_por"] == "boss@x.com"
    assert (_get(con, outro)["categoria_id"], _get(con, outro)["categoria_origem"]) == (2, "regra")


def test_sempre_assim_sem_decisao_sua_levanta(con):
    a = _l(con, 1)
    with pytest.raises(ValueError):
        sempre_assim(con, a, por="x")


def test_sempre_assim_escapa_o_estabelecimento(con):
    a = _l(con, 1, "LOJA (X) +", "LOJA (X) +", categoria_id=2, categoria_origem="voce")
    rid = sempre_assim(con, a, por="x")
    assert _l(con, 99, "LOJA (X) + FILIAL", "LOJA (X) +")  # não quebra com metacaracteres
    import re
    assert re.search(con.execute("select padrao from regra where id=?", (rid,)).fetchone()[0], "LOJA (X) + FILIAL", re.I)


def test_ligar_regra_aplica_ao_passado_e_desligar_nao_desfaz(con):
    con.execute("insert into regra(padrao, acao, ativa, criado_em, criada_por) values ('UBER', ?, 0, '2026-10-08', 'gabi')", (json.dumps({"categoria_id": 2}),))
    a = _l(con, 1)
    definir_ativa(con, 1, True, por="boss@x.com")
    assert con.execute("select ativa from regra").fetchone()[0] == 1 and _get(con, a)["categoria_id"] == 2
    definir_ativa(con, 1, False, por="boss@x.com")
    assert con.execute("select ativa from regra").fetchone()[0] == 0 and _get(con, a)["categoria_id"] == 2  # o que já foi feito fica
    assert con.execute("select count(*) from decisao where o_que like 'regra %'").fetchone()[0] == 2


def test_definir_ativa_regra_inexistente(con):
    with pytest.raises(LookupError):
        definir_ativa(con, 999, True, por="x")


def test_criar_regra_ativa_aplica_ao_passado_audita_e_e_idempotente(con):
    a = _l(con, 1, desc="MERCADOLIVRE PROD", estab="MERCADOLIVRE")
    b = _l(con, 2, desc="MERCADOLIVRE PROD", estab="MERCADOLIVRE", para_quem_id="p1", para_quem_origem="voce")
    rid = criar_regra_ativa(con, "MERCADOLIVRE", {"categoria_id": 1}, "ricardo (via Claude)")
    assert rid and con.execute("select ativa from regra where id=?", (rid,)).fetchone()[0] == 1
    assert _get(con, a)["categoria_id"] == 1 and _get(con, a)["categoria_origem"] == "regra"
    assert _get(con, b)["categoria_id"] == 1
    assert con.execute("select count(*) from decisao where quem='ricardo (via Claude)' and o_que like '%regra%'").fetchone()[0] == 1
    assert criar_regra_ativa(con, "MERCADOLIVRE", {"categoria_id": 1}, "x") is None   # mesmo padrão: não duplica
    assert con.execute("select count(*) from regra").fetchone()[0] == 1


def test_criar_regra_ativa_nunca_sobrescreve_o_que_o_ricardo_decidiu(con):
    lid = _l(con, 1, categoria_id=2, categoria_origem="voce")
    criar_regra_ativa(con, "UBER", {"categoria_id": 1}, "r")
    assert _get(con, lid)["categoria_id"] == 2


def test_criar_regra_ativa_valida_o_padrao_e_a_acao(con):
    for padrao, acao in (("", {"categoria_id": 1}), ("(", {"categoria_id": 1}), ("X", {}), ("X", {"categoria_id": 999}), ("X", {"para_quem_id": "fantasma"})):
        with pytest.raises(ValueError):
            criar_regra_ativa(con, padrao, acao, "r")
    assert con.execute("select count(*) from regra").fetchone()[0] == 0
