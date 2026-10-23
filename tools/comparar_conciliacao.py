"""Compara o resultado da conciliação antiga (cópia congelada) com a do código atual, sobre uma cópia do banco só leitura.
Uso: python -m tools.comparar_conciliacao [--banco /var/lib/gabi-brain/gabi.db] [--hoje AAAA-MM-DD]
Mostra o compromisso cujo estado ou lançamento (tx_id) mudou. Trocas esperadas de estado não contam (previsto → aberto
e debito_automatico → aberto), a menos que o lançamento também mude."""
import argparse
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from gabi.dinheiro import caixa, compromissos, conciliacao, repositorio
from tools._conciliacao_antiga.fontes import rodar_antigo

_ESPERADAS = {("previsto", "aberto"), ("debito_automatico", "aberto")}


def _rodar_novo(con, hoje: date, agora: datetime) -> dict:
    """gerar + conciliar do código atual, sem gravar: {comp_id: (nome, vencimento, estado, motivo, tx_id)}."""
    leitura = repositorio.ler_leitura(con)
    comps = compromissos.gerar(repositorio.FontesBanco(con), leitura, [], hoje, [])
    donos = caixa.dono_tokens(repositorio.titulares(con)) or None
    pagos = compromissos.valores_em_centavos(leitura["valores"])
    res, _ = conciliacao.conciliar(comps, repositorio.txs_para_conciliar(con, hoje), repositorio.vinculos(con),
                                   repositorio.estado_contas(con), pagos, leitura["params"], hoje, agora, donos)
    return {c["id"]: (c["nome"], c["vencimento"], res[c["id"]]["estado"], res[c["id"]].get("motivo"), res[c["id"]].get("tx_id"))
            for c in comps if c["id"] in res}


def comparar(con, hoje: date, agora: datetime) -> list[dict]:
    """Compromissos cujo estado ou lançamento mudou entre o antigo e o novo (ausente de um lado conta como None).
    Documentos avulsos não entram na comparação (docs=() dos dois lados, como na rodada de produção)."""
    antigo, novo = rodar_antigo(con, hoje, agora), _rodar_novo(con, hoje, agora)
    saida = []
    for cid in sorted(set(antigo) | set(novo)):
        a, n = antigo.get(cid), novo.get(cid)
        antes, depois = a[2] if a else None, n[2] if n else None
        tx_antes, tx_depois = a[4] if a else None, n[4] if n else None
        if tx_antes == tx_depois and (antes == depois or (antes, depois) in _ESPERADAS):
            continue
        nome, venc = (n or a)[0], (n or a)[1]
        saida.append({"id": cid, "nome": nome, "vencimento": venc, "antes": antes, "depois": depois,
                      "tx_antes": tx_antes, "tx_depois": tx_depois, "motivo": n[3] if n else None})
    return saida


def _com_tx(estado, tx):
    return f"{estado}({tx})" if tx else str(estado)


def imprimir(difs: list[dict]) -> None:
    print("(documentos avulsos não são comparados)")
    for d in difs:
        print(f"{d['id']} | {d['nome']} | {d['vencimento']} | {_com_tx(d['antes'], d['tx_antes'])} → "
              f"{_com_tx(d['depois'], d['tx_depois'])} | {d['motivo'] or ''}")
    print(f"{len(difs)} diferença(s)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--hoje", default=None, help="AAAA-MM-DD (padrão: hoje)")
    a = ap.parse_args(argv)
    hoje = date.fromisoformat(a.hoje) if a.hoje else date.today()
    agora = datetime.now().astimezone() if not a.hoje else datetime.fromisoformat(f"{a.hoje}T12:00:00-03:00")
    origem = sqlite3.connect(f"file:{Path(a.banco)}?mode=ro", uri=True)
    con = sqlite3.connect(":memory:")
    origem.backup(con)
    origem.close()
    con.row_factory = sqlite3.Row
    imprimir(comparar(con, hoje, agora))
    return 0


if __name__ == "__main__":
    sys.exit(main())
