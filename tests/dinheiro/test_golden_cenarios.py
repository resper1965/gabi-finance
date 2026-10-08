"""Prova que gerar + conciliar portados reproduzem o gabi-fin em cenários completos (entradas sintéticas)."""
import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.dinheiro import caixa, compromissos, conciliacao
from tools.golden import _ser

CASOS = json.loads((Path(__file__).parent.parent / "golden" / "cenarios.json").read_text(encoding="utf-8"))


class Fontes:
    """O que o `gerar` precisa do banco, montado a partir da entrada do cenário (mesma semântica das consultas originais)."""

    def __init__(self, e):
        self.e = e

    def debitos(self, hoje):
        pj = {k["account_id"] for k in self.e["conta_estado"] if k["pj"]}
        rows = [t for t in self.e["tx"] if t["tipo_conta"] == "BANK" and t["valor"] < 0 and t["data"][:10] <= hoje.isoformat()
                and t["account_id"] not in pj]
        rows.sort(key=lambda t: t["id"])
        rows.sort(key=lambda t: t["data"], reverse=True)
        return [(t["descricao"], t["valor"], t["data"], t["account_id"], t["id"]) for t in rows]

    def faturas(self):
        nomes = {k["account_id"]: k["nome"] for k in self.e["contas"]}
        return [{"account_id": f["account_id"], "nome": nomes.get(f["account_id"]) or "", "vencimento": f["vencimento"][:10],
                 "total": f["total"], "status": f["payment_status"]} for f in self.e["faturas"] if f["vencimento"]]

    def anterior(self):
        return {a["id"]: (a["valor"], a["valor_fonte"]) for a in self.e["anterior"]}


def _rodar(e):
    hoje, agora = dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"])
    invalidas = []
    comps = compromissos.gerar(Fontes(e), {"linhas": e["linhas"], "valores": e["valores"], "params": e["params"]}, e["docs"], hoje, invalidas)
    estado = {k["account_id"]: {kk: k[kk] for kk in ("tipo", "pj", "banco", "nome", "ult_sync_ok", "ult_tx_real")} for k in e["conta_estado"]}
    donos = caixa.dono_tokens(e["donos"]) if e["donos"] else None
    res, novos = conciliacao.conciliar(comps, e["tx"], e["vinculos"], estado, e["valores"], e["params"], hoje, agora, donos)
    return invalidas, comps, res, novos


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["args"][0])
def test_porte_reproduz_o_gabi_fin(caso):
    saida = caso["saida"]
    invalidas, comps, res, novos = _rodar(saida["entrada"])
    assert _ser(invalidas) == saida["invalidas"]
    assert _ser(comps) == saida["comps"]
    assert _ser(res) == saida["conciliacao"]["res"]
    assert _ser(novos) == saida["conciliacao"]["novos"]


def test_os_cenarios_exercitam_os_estados_principais():
    estados = {v["estado"] for c in CASOS for v in c["saida"]["conciliacao"]["res"].values()}
    assert {"pago", "aberto", "atrasado", "a_conferir", "debito_automatico"} <= estados
    metodos = {v["metodo"] for c in CASOS for v in c["saida"]["conciliacao"]["res"].values()}
    assert {"favorecido", "manual", "valor", "emissor"} <= metodos
