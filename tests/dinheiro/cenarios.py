"""Cenários (tests/dinheiro/cenarios.json: [{"nome", "entrada"}]) e o carregador que os põe nas tabelas novas."""
import json
from pathlib import Path

from gabi.dinheiro import repositorio
from gabi.dinheiro.valor import para_centavos

CASOS = json.loads((Path(__file__).parent / "cenarios.json").read_text(encoding="utf-8"))


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
