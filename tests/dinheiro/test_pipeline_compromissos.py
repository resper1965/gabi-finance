"""O pipeline sobre o banco (repositório + gerar + conciliar + gravar), sobre os cenários de tests/dinheiro/cenarios.json."""
import datetime as dt
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import repositorio
from gabi.dinheiro.contas_pagar import atualizar_compromissos
from tests.dinheiro.cenarios import CASOS, carregar_cenario
from tools.golden import _ser

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_rodar_duas_vezes_e_idempotente(con):
    caso = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    carregar_cenario(con, caso)
    h, a = dt.date.fromisoformat(caso["hoje"]), dt.datetime.fromisoformat(caso["agora"])
    atualizar_compromissos(con, h, a, docs=caso["docs"])
    antes = [tuple(r) for r in con.execute("select id, estado, valor_centavos, motivo, dados from compromisso order by id")]
    n1 = con.execute("select count(*) from conciliacao").fetchone()[0]
    atualizar_compromissos(con, h, a, docs=caso["docs"])
    assert [tuple(r) for r in con.execute("select id, estado, valor_centavos, motivo, dados from compromisso order by id")] == antes
    assert con.execute("select count(*) from conciliacao").fetchone()[0] == n1


def test_leitura_volta_igual_ao_que_foi_gravado(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    L = repositorio.ler_leitura(con)
    assert _ser(L["linhas"]) == _ser(e["linhas"]) and _ser(L["valores"]) == _ser(e["valores"])
    for k, v in e["params"].items():
        assert L["params"][k] == v
    assert isinstance(L["params"]["bancos_pj"], set) and isinstance(L["params"]["horas_envio"], set)


def test_linha_inativa_ou_excluida_nao_entra_na_leitura(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    con.execute("update compromisso_linha set ativo=0 where id='aluguel'")
    con.execute("update compromisso_linha set excluido_em='2026-10-08' where id='energia'")
    ids = {l["id"] for l in repositorio.ler_leitura(con)["linhas"]}
    assert "aluguel" not in ids and "energia" not in ids and "escola" in ids
    assert all(v["compromisso"] in ids for v in repositorio.ler_leitura(con)["valores"])  # valor de linha inativa some junto


def test_gravar_leitura_substitui_o_conteudo_anterior(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    repositorio.gravar_leitura(con, {"linhas": e["linhas"][:2], "params": {}, "valores": []})
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == 2
    assert con.execute("select count(*) from valor_do_mes").fetchone()[0] == 0
    assert repositorio.ler_leitura(con)["params"]["janela_antes_dias"] == 10  # sem valor gravado: volta o padrão


def test_gravar_leitura_e_atomico(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    ruim = {"linhas": [e["linhas"][0], {**e["linhas"][1], "valor_tipo": "invalido"}], "params": {}, "valores": []}
    with pytest.raises(Exception):
        repositorio.gravar_leitura(con, ruim)
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == len(e["linhas"])  # nada mudou


def test_pagamento_ainda_pendente_ja_concilia_como_no_gabi_fin(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    carregar_cenario(con, e)
    con.execute("update lancamento set status='pending' where externo_id='t1'")  # o Pix do aluguel ainda não foi 'posted'
    atualizar_compromissos(con, dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"]), docs=e["docs"])
    assert con.execute("select estado from compromisso where id='aluguel:2026-10'").fetchone()[0] == "pago"


def _base(con):
    e = next(c for c in CASOS if c["nome"] == "base")["entrada"]
    carregar_cenario(con, e)
    return e, dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"])


def test_debito_de_conta_pj_nao_paga_conta_pessoal(con):
    e, h, a = _base(con)
    con.execute("delete from lancamento where externo_id='t1'")  # tira o Pix do aluguel da conta pessoal
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj77','C6 PJ','BANK','Conta PJ',1,'sim')")
    con.execute("insert into conta_estado(account_id, banco, nome, tipo, pj, ult_sync_ok, status_conexao, saldo_centavos, atualizado_em) "
                "values ('pj77','C6 PJ','Conta PJ','BANK',1,'2026-10-08T14:00:00-03:00','OK',0,'2026-10-08')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) "
                "values ((select id from conta where externo_id='pj77'),'tpj','2026-10-05',-200000,'PIX ENVIADO IMOBILIARIA SUL','posted')")
    atualizar_compromissos(con, h, a, docs=e["docs"])
    assert con.execute("select estado from compromisso where id='aluguel:2026-10'").fetchone()[0] == "atrasado"  # PJ não paga a PF


def test_ultimo_pagamento_vem_do_debito_mais_recente(con):
    e, h, a = _base(con)
    con.execute("delete from valor_do_mes")
    e["docs"] = []
    ana = con.execute("select id from conta where externo_id='a1234'").fetchone()[0]
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (?,?,?,?,?, 'posted')",
                (ana, "t-velho", "2026-08-10", -19000, "BOLETO ENEL DISTRIBUICAO"))
    atualizar_compromissos(con, h, a, docs=[])
    r = con.execute("select valor_centavos, valor_fonte from compromisso where id='energia:2026-10'").fetchone()
    assert (r["valor_centavos"], r["valor_fonte"]) == (21540, "ultimo")  # setembro (R$ 215,40), não agosto (R$ 190,00)


def test_baixa_manual_que_sai_dos_cadastros_e_desfeita(con):
    e = next(c for c in CASOS if c["nome"] == "baixa_manual")["entrada"]
    carregar_cenario(con, e)
    h, a = dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"])
    atualizar_compromissos(con, h, a, docs=e["docs"])
    assert con.execute("select estado from compromisso where id='iptu:2026-10'").fetchone()[0] == "pago"
    assert con.execute("select count(*) from conciliacao where tx_id like 'manual:%'").fetchone()[0] == 1
    con.execute("delete from valor_do_mes where tipo='pago'")
    atualizar_compromissos(con, h, a, docs=e["docs"])
    assert con.execute("select estado from compromisso where id='iptu:2026-10'").fetchone()[0] == "atrasado"
    assert con.execute("select count(*) from conciliacao where tx_id like 'manual:%'").fetchone()[0] == 0


def test_primeiro_vinculo_de_um_lancamento_fica(con):
    e, h, a = _base(con)
    atualizar_compromissos(con, h, a, docs=e["docs"])
    antes = con.execute("select compromisso_id from conciliacao where tx_id='t1'").fetchone()[0]
    repositorio.gravar_resultado(con, [], {}, [("t1", "outro:2026-10", "valor", 0)], a)  # tentativa de religar o mesmo lançamento
    assert [tuple(r) for r in con.execute("select compromisso_id from conciliacao where tx_id='t1'")] == [(antes,)]
    assert con.execute("select count(*) from conciliacao where tx_id='t1'").fetchone()[0] == 1  # um lançamento paga um compromisso só
