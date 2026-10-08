"""O pipeline sobre o BANCO NOVO (repositório + gerar + conciliar + gravar) tem de dar o mesmo que o gabi-fin deu."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import repositorio
from gabi.dinheiro.contas_pagar import atualizar_compromissos
from gabi.dinheiro.valor import para_centavos
from tools.golden import _ser

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
CASOS = json.loads((Path(__file__).parent.parent / "golden" / "cenarios.json").read_text(encoding="utf-8"))


def _cent(v):
    return None if v is None else para_centavos(round(v, 2))


def carregar_cenario(con, e):
    """Põe a entrada do cenário nas tabelas novas (conta, lancamento, fatura, conta_estado, cadastros...)."""
    ids = {}
    for k in e["contas"]:
        pj = next((x["pj"] for x in e["conta_estado"] if x["account_id"] == k["account_id"]), 0)
        con.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado, vencimento_fatura) values (?,?,?,?,?, 'sim', ?)",
                    (k["account_id"], k["banco"], k["tipo"], k["nome"], pj, k["vencimento"]))
        ids[k["account_id"]] = con.execute("select id from conta where externo_id=?", (k["account_id"],)).fetchone()[0]
    for k in e["conta_estado"]:
        if k["account_id"] not in ids:
            con.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values (?,?,?,?,?, 'sim')",
                        (k["account_id"], k["banco"], k["tipo"], k["nome"], k["pj"]))
            ids[k["account_id"]] = con.execute("select id from conta where externo_id=?", (k["account_id"],)).fetchone()[0]
        con.execute("insert into conta_estado(account_id, banco, nome, tipo, pj, ult_tx_real, ult_sync_ok, status_conexao, saldo_centavos, atualizado_em) "
                    "values (?,?,?,?,?,?,?, 'OK', 0, '2026-10-08')",
                    (k["account_id"], k["banco"], k["nome"], k["tipo"], k["pj"], k["ult_tx_real"], k["ult_sync_ok"]))
    for t in e["tx"]:
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_banco, natureza, status) "
                    "values (?,?,?,?,?,?,?, 'posted')",
                    (ids[t["account_id"]], t["id"], t["data"], _cent(t["valor"]), t["descricao"], t["categoria"], t["natureza"]))
    for f in e["faturas"]:
        con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values (?,?,?,?,?,?)",
                    (f["id"], f["account_id"], f["vencimento"], _cent(f["total"]), f["payment_status"], ids[f["account_id"]]))
    for a in e["anterior"]:
        con.execute("insert into compromisso(id, valor_centavos, valor_fonte) values (?,?,?)", (a["id"], _cent(a["valor"]), a["valor_fonte"]))
    for tx_id, comp_id in e["vinculos"].items():
        con.execute("insert into conciliacao(tx_id, compromisso_id, metodo, criado_em) values (?,?, 'vinculo', '2026-10-01')", (tx_id, comp_id))
    leitura = {"linhas": e["linhas"], "params": {**e["params"]}, "valores": e["valores"]}
    repositorio.gravar_leitura(con, leitura)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["args"][0])
def test_banco_novo_reproduz_o_gabi_fin(con, caso):
    s = caso["saida"]
    e = s["entrada"]
    carregar_cenario(con, e)
    atualizar_compromissos(con, dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"]), docs=e["docs"])
    esperado = {c["id"]: c for c in s["comps"]}
    gravado = {r["id"]: r for r in con.execute("select * from compromisso")}
    assert set(gravado) == set(esperado)  # os mesmos compromissos (inclusive faturas e documentos avulsos)
    res = s["conciliacao"]["res"]
    for cid, comp in esperado.items():
        r, g = res[cid], gravado[cid]
        assert g["estado"] == r["estado"] and g["motivo"] == r["motivo"], cid
        assert (g["nome"], g["vencimento"], g["vencimento_util"], g["valor_fonte"], g["forma"], g["origem"]) == (
            comp["nome"], comp["vencimento"], comp["vencimento_util"], comp["valor_fonte"], comp["forma"], comp["origem"]), cid
        assert g["valor_centavos"] == _cent(comp["valor"]), cid
        dados = json.loads(g["dados"])
        for k in ("metodo", "tx_id", "pago_em", "diferenca", "juros"):
            assert dados[k] == r[k], (cid, k)
    # vínculos novos que o gabi-fin gravaria
    novos = {(t, c) for t, c, m, d in s["conciliacao"]["novos"] if not t.startswith("manual:")}
    assert {(r["tx_id"], r["compromisso_id"]) for r in con.execute("select tx_id, compromisso_id from conciliacao")} >= novos


def test_rodar_duas_vezes_e_idempotente(con):
    caso = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    carregar_cenario(con, caso)
    h, a = dt.date.fromisoformat(caso["hoje"]), dt.datetime.fromisoformat(caso["agora"])
    atualizar_compromissos(con, h, a, docs=caso["docs"])
    antes = [tuple(r) for r in con.execute("select id, estado, valor_centavos, motivo, dados from compromisso order by id")]
    n1 = con.execute("select count(*) from conciliacao").fetchone()[0]
    atualizar_compromissos(con, h, a, docs=caso["docs"])
    assert [tuple(r) for r in con.execute("select id, estado, valor_centavos, motivo, dados from compromisso order by id")] == antes
    assert con.execute("select count(*) from conciliacao").fetchone()[0] == n1


def test_leitura_volta_igual_ao_que_foi_gravado(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    L = repositorio.ler_leitura(con)
    assert _ser(L["linhas"]) == _ser(e["linhas"]) and _ser(L["valores"]) == _ser(e["valores"])
    for k, v in e["params"].items():
        assert L["params"][k] == v
    assert isinstance(L["params"]["bancos_pj"], set) and isinstance(L["params"]["horas_envio"], set)


def test_linha_inativa_ou_excluida_nao_entra_na_leitura(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    con.execute("update compromisso_linha set ativo=0 where id='aluguel'")
    con.execute("update compromisso_linha set excluido_em='2026-10-08' where id='energia'")
    ids = {l["id"] for l in repositorio.ler_leitura(con)["linhas"]}
    assert "aluguel" not in ids and "energia" not in ids and "escola" in ids
    assert all(v["compromisso"] in ids for v in repositorio.ler_leitura(con)["valores"])  # valor de linha inativa some junto


def test_gravar_leitura_substitui_o_conteudo_anterior(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    repositorio.gravar_leitura(con, {"linhas": e["linhas"][:2], "params": {}, "valores": []})
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == 2
    assert con.execute("select count(*) from valor_do_mes").fetchone()[0] == 0
    assert repositorio.ler_leitura(con)["params"]["janela_antes_dias"] == 10  # sem valor gravado: volta o padrão


def test_gravar_leitura_e_atomico(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    repositorio.gravar_leitura(con, {"linhas": e["linhas"], "params": e["params"], "valores": e["valores"]})
    ruim = {"linhas": [e["linhas"][0], {**e["linhas"][1], "valor_tipo": "invalido"}], "params": {}, "valores": []}
    with pytest.raises(Exception):
        repositorio.gravar_leitura(con, ruim)
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == len(e["linhas"])  # nada mudou


def test_pagamento_ainda_pendente_ja_concilia_como_no_gabi_fin(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
    carregar_cenario(con, e)
    con.execute("update lancamento set status='pending' where externo_id='t1'")  # o Pix do aluguel ainda não foi 'posted'
    atualizar_compromissos(con, dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"]), docs=e["docs"])
    assert con.execute("select estado from compromisso where id='aluguel:2026-10'").fetchone()[0] == "pago"


def _base(con):
    e = next(c for c in CASOS if c["args"][0] == "base")["saida"]["entrada"]
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
    e = next(c for c in CASOS if c["args"][0] == "baixa_manual")["saida"]["entrada"]
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
    repositorio.gravar_resultado(con, [], {}, [("t1", "outro:2026-10", "valor", 0.0)], a)  # tentativa de religar o mesmo lançamento
    assert [tuple(r) for r in con.execute("select compromisso_id from conciliacao where tx_id='t1'")] == [(antes,)]
    assert con.execute("select count(*) from conciliacao where tx_id='t1'").fetchone()[0] == 1  # um lançamento paga um compromisso só
