"""As análises portadas, lendo o BANCO NOVO, reproduzem o gabi-fin nas mesmas entradas sintéticas."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import analise, repositorio
from gabi.dinheiro.valor import para_centavos
from tools import golden
from tools.golden import _ser

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
GOLDEN = {(c["fn"], json.dumps(c["args"], sort_keys=True)): c for c in json.loads((Path(__file__).parent.parent / "golden" / "finlib.json").read_text(encoding="utf-8"))}


def _cent(v):
    return None if v is None else para_centavos(round(v, 2))


def carregar(con, tx, contas=(), faturas=()):
    """Linhas no formato do fin.db do gabi-fin -> tabelas novas."""
    ids = {}

    def conta(ext, tipo, nome=None, banco=None, venc=None, limite=None, disp=None):
        if ext not in ids:
            con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado, vencimento_fatura, limite_centavos, disponivel_centavos) "
                        "values (?,?,?,?, 'sim', ?,?,?)", (ext, banco or "Banco", tipo, nome or ext, venc, _cent(limite), _cent(disp)))
            ids[ext] = con.execute("select id from conta where externo_id=?", (ext,)).fetchone()[0]
        return ids[ext]

    for ts, aid, tipo, nome, banco, saldo, limite, disp, venc in contas:
        cid = conta(aid, tipo, nome, banco, venc, limite, disp)
        con.execute("insert into saldo(conta_id, em, saldo_centavos) values (?,?,?)", (cid, ts, _cent(saldo)))
    for (i, aid, tipo, data, desc, valor, cat, op, met, parcela, parcelas, dc, fat, nat, raw) in tx:
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, categoria_banco, natureza, parcela, parcelas, status) "
                    "values (?,?,?,?,?,?,?,?,?, 'posted')", (conta(aid, tipo), i, data, _cent(valor), desc, cat, nat, parcela, parcelas))
    for fid, aid, venc, total, minimo, raw in faturas:
        con.execute("insert into fatura(id, account_id, vencimento, total_centavos, minimo_centavos, conta_id) values (?,?,?,?,?,?)",
                    (fid, aid, venc, _cent(total), _cent(minimo), conta(aid, "CREDIT")))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _caso(fn, *args):
    return GOLDEN[(fn, json.dumps(list(args), sort_keys=True))]["saida"]


H = dt.date(2026, 10, 8)


@pytest.mark.parametrize("visao", ["caixa", "custo"])
def test_recorrentes(con, visao):
    carregar(con, golden._historico())
    assert _ser(analise.recorrentes(repositorio.FonteAnalise(con), visao, H)) == _caso("_w_recorrentes", visao, "2026-10-08")


@pytest.mark.parametrize("por", ["categoria", "descricao"])
def test_gastos(con, por):
    carregar(con, golden.dados_gastos())
    assert _ser(analise.gastos(repositorio.FonteAnalise(con), "2026-09-01", "2026-09-30", por)) == _caso("_w_gastos", "2026-09-01", "2026-09-30", por)


@pytest.mark.parametrize("extra", [None, {"data": "2026-10-15", "valor": 500.0, "descricao": "compra"}])
def test_previsao(con, extra):
    tx, contas, faturas = golden.dados_previsao()
    carregar(con, tx, contas, faturas)
    assert _ser(analise.previsao(repositorio.FonteAnalise(con), 30, extra, H)) == _caso("_w_previsao", 30, extra, "2026-10-08")


def test_vazamentos(con):
    carregar(con, golden.dados_vazamentos())
    assert _ser(analise.vazamentos(repositorio.FonteAnalise(con), 3, H)) == _caso("_w_vazamentos", 3, "2026-10-08")


def test_gastos_usam_a_classificacao_do_ricardo_e_nao_o_banco(con):
    carregar(con, golden.dados_gastos())
    con.execute("insert into categoria(nome) values ('Padaria e lanche')")
    con.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    con.execute("update lancamento set categoria_id=1, categoria_origem='voce', para_quem_id='p1', para_quem_origem='voce' where externo_id='t1'")
    r = analise.gastos(repositorio.FonteAnalise(con), "2026-09-01", "2026-09-30", "categoria")
    assert "Padaria e lanche" in {i["chave"] for i in r["itens"]} and "Food" not in {i["chave"] for i in r["itens"]}
    p = analise.gastos(repositorio.FonteAnalise(con), "2026-09-01", "2026-09-30", "pessoa")
    assert {i["chave"] for i in p["itens"]} == {"Ana", "(sem pessoa)"}


def test_sem_nenhum_dado_nao_quebra(con):
    f = repositorio.FonteAnalise(con)
    assert analise.recorrentes(f, "caixa", H) == []
    assert analise.gastos(f, "2026-09-01", "2026-09-30")["total_custo"] == 0
    p = analise.previsao(f, 30, None, H)
    assert p["saldo_inicial"] == 0 and p["eventos"] == [] and p["dados_de"] is None
    assert analise.vazamentos(f, 3, H)["tarifas_juros"] == []


def test_parcela_ja_quitada_nao_gera_parcela_futura(con):
    tx, contas, faturas = golden.dados_previsao()
    quitada = golden._tx(901, "2026-09-03", "COMPRA QUITADA", -100.0, conta="c9999", tipo="CREDIT", natureza="custo", parcela=5, parcelas=5)
    carregar(con, tx + [quitada], contas, faturas)
    descr = [e["descricao"] for e in analise.previsao(repositorio.FonteAnalise(con), 120, None, H)["eventos"]]
    assert any("COMPRA PARCELADA" in d for d in descr) and not any("COMPRA QUITADA" in d for d in descr)
