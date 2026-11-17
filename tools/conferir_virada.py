"""Conferência da virada (docs/virada.md, passo 6): imprime, de UM banco, o que precisa bater entre o serviço anterior e o gabi-finance:
saldos por conta do caixa único, total A pagar do mês e a projeção de caixa de 30 dias. Só leitura (abre o arquivo com mode=ro) e SEM migrar:
roda igual sobre a cópia do banco antigo (esquema 0089) e sobre o banco já migrado (0091). A saída é determinística para o mesmo banco e a mesma data,
então a conferência é: rodar nos dois e comparar com `diff` (sem diferença = bateu).

Uso: python -m tools.conferir_virada --banco /caminho/gabi.db [--hoje AAAA-MM-DD]
Consome: dinheiro.contas_pagar (caixa único), dinheiro.projecao, dinheiro.valor, hoje."""
import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

from gabi.dinheiro import contas_pagar, projecao
from gabi.dinheiro.valor import formatar
from gabi.hoje import hoje_brt

ESTADOS_A_PAGAR = ("aberto", "atrasado", "a_conferir")


def _abrir(banco: Path) -> sqlite3.Connection:
    """Somente leitura. Se o arquivo está em WAL e a pasta não deixa criar o -shm, tenta de novo como imutável (a cópia não está em uso)."""
    if not Path(banco).is_file():
        raise FileNotFoundError(f"banco não encontrado: {banco}")
    for modo in ("mode=ro", "mode=ro&immutable=1"):
        con = sqlite3.connect(f"file:{banco}?{modo}", uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("select count(*) from sqlite_master").fetchone()
            return con
        except sqlite3.OperationalError:
            con.close()
    raise sqlite3.OperationalError(f"não consegui abrir {banco} para leitura")


def _r(centavos: int | None) -> str:
    return "-" if centavos is None else formatar(centavos)


def conferir(con: sqlite3.Connection, hoje: dt.date) -> list[str]:
    mes = hoje.isoformat()[:7]
    saida = [f"conferencia-virada v1 hoje={hoje.isoformat()}", "", "== saldos por conta (caixa unico: contas BANK liberadas) =="]
    cx = contas_pagar.caixa_unico(con, hoje)
    for c in sorted(cx.contas, key=lambda c: (c["apelido"], c["em"])):
        saida.append(f"{c['apelido']}\t{_r(c['saldo_centavos'])}\t{c['em']}")
    saida += [f"total\t{_r(cx.saldo_centavos)}", f"faturas_abertas\t{_r(cx.faturas_abertas_centavos)}", "",
              f"== a pagar em {mes} (compromissos do mes que nao estao pagos) =="]
    total_n = total_v = 0
    for estado in ESTADOS_A_PAGAR:
        n, v = con.execute("select count(*), coalesce(sum(valor_centavos), 0) from compromisso where substr(vencimento_util, 1, 7)=? and estado=?",
                           (mes, estado)).fetchone()
        saida.append(f"{estado}\t{n}\t{_r(v)}")
        total_n, total_v = total_n + n, total_v + v
    sem_valor = con.execute("select count(*) from compromisso where substr(vencimento_util, 1, 7)=? and estado in (?, ?, ?) and valor_centavos is null",
                            (mes, *ESTADOS_A_PAGAR)).fetchone()[0]
    saida += [f"total\t{total_n}\t{_r(total_v)}", f"sem_valor\t{sem_valor}", "", "== projecao de caixa, 30 dias (dia, entradas, saidas, saldo) =="]
    serie = projecao.projetar(con, hoje, 30)
    for d in serie:
        saida.append(f"{d['dia']}\t{_r(d['entradas_centavos'])}\t{_r(d['saidas_centavos'])}\t{_r(d['saldo_centavos'])}")
    menor = min(serie, key=lambda d: (d["saldo_centavos"], d["dia"]))
    saida.append(f"menor_saldo\t{menor['dia']}\t{_r(menor['saldo_centavos'])}")
    return saida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Saldos, A pagar do mês e projeção de 30 dias de um banco (só leitura).")
    ap.add_argument("--banco", required=True, help="caminho do gabi.db (do serviço anterior ou do gabi-finance)")
    ap.add_argument("--hoje", help="AAAA-MM-DD (padrão: hoje em Brasília); use a MESMA data nas duas conferências")
    a = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else hoje_brt()
    try:
        con = _abrir(Path(a.banco))
    except (FileNotFoundError, sqlite3.Error) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    try:
        print("\n".join(conferir(con, hoje)))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
