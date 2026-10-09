"""Compara a agenda de compromissos do gabi.brain com a do gabi-financeiro (critério de corte da virada, G21).
Somente leitura dos dois lados. Divergência vira ajuste de cadastro, não de código.
Uso: python -m tools.comparar_agenda [--mes AAAA-MM] [--banco ...] [--financeiro /var/lib/gabi-fin/compromissos.json]"""
import json
import sys
from datetime import date
from pathlib import Path

SECOES = ("atrasadas", "proximos_7_dias", "pagas_desde_ultima", "a_conferir")


def _centavos(reais) -> int:
    return round(float(reais) * 100)


def comparar(brain_con, compromissos_json: Path, mes: str) -> list[dict]:
    """Divergências do mês. O JSON do financeiro só cobre uma janela de datas: do lado do brain só conta o que cai dentro dela."""
    dados = json.loads(Path(compromissos_json).read_text(encoding="utf-8"))
    fin = {i["id"]: i for s in SECOES for i in dados.get(s) or [] if str(i.get("id", "")).endswith(f":{mes}")}
    if not fin:
        return []
    vencs = [i["vencimento"] for i in fin.values() if i.get("vencimento")]
    ini, fim = min(vencs), max(vencs)
    brain = {r[0]: r for r in brain_con.execute(
        "select id, valor_centavos, coalesce(vencimento_util, vencimento) from compromisso where id like ?", (f"%:{mes}",))}
    saida = []
    for linha in sorted(set(fin) | set(brain)):
        f, b = fin.get(linha), brain.get(linha)
        if b and not f:
            if ini <= (b[2] or "") <= fim:
                saida.append({"linha": linha, "so_no_brain": True, "so_no_financeiro": False, "valor_diferente": None})
        elif f and not b:
            saida.append({"linha": linha, "so_no_brain": False, "so_no_financeiro": True, "valor_diferente": None})
        elif f.get("valor") is not None and b[1] is not None and _centavos(f["valor"]) != b[1]:
            saida.append({"linha": linha, "so_no_brain": False, "so_no_financeiro": False,
                          "valor_diferente": {"brain": b[1], "financeiro": _centavos(f["valor"])}})
    return saida


def main(banco: Path, arquivo: Path, mes: str) -> int:
    from gabi.db import conectar
    con = conectar(banco)
    try:
        div = comparar(con, arquivo, mes)
    except (OSError, ValueError) as e:
        print(f"comparar_agenda: não consegui ler os dados: {e}")
        return 2
    for d in div:
        print(json.dumps(d, ensure_ascii=False))
    print(f"comparar_agenda {mes}: {len(div)} divergência(s)" + (" — corte liberado se for 0 por 7 dias" if not div else ""))
    return 1 if div else 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    ap.add_argument("--financeiro", default="/var/lib/gabi-fin/compromissos.json")
    ap.add_argument("--mes", default=date.today().strftime("%Y-%m"))
    a = ap.parse_args()
    sys.exit(main(Path(a.banco), Path(a.financeiro), a.mes))
