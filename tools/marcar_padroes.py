"""Corrige a origem dos "para quem" que vieram de padrões do cadastro (cartão, categoria, compromisso, responsável) mas foram gravados
como 'regra': passam a 'fonte', para que uma regra por estabelecimento que o Ricardo dita possa sobrescrevê-los. Um 'regra' que casa com
uma regra ATIVA que define para_quem continua 'regra'. Idempotente. Uso: python -m tools.marcar_padroes [--banco CAMINHO]."""
import argparse
import json
import re

from gabi.db import conectar, transacao
from gabi.dinheiro.regras import casa


def marcar_origem_padrao(con) -> int:
    regras = []
    for r in con.execute("select padrao, acao from regra where ativa=1"):
        try:
            if json.loads(r["acao"]).get("para_quem_id") is not None:
                regras.append(re.compile(r["padrao"], re.I))
        except (ValueError, re.error):
            continue
    n = 0
    with transacao(con):
        for l in con.execute("select id, descricao_original, estabelecimento from lancamento where para_quem_origem='regra' and para_quem_id is not null").fetchall():
            if not any(casa(rx, l["descricao_original"], l["estabelecimento"]) for rx in regras):
                con.execute("update lancamento set para_quem_origem='fonte' where id=?", (l["id"],))
                n += 1
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="/var/lib/gabi-brain/gabi.db")
    print(f"marcados como padrão do cadastro: {marcar_origem_padrao(conectar(ap.parse_args().banco))}")
