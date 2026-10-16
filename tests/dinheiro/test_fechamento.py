import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.fechamento import SEM_MOVIMENTO, montar

HOJE = dt.date(2026, 10, 16)
MIGR = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','Itau','BANK','Itaú','sim')")       # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Outro','BANK','Outro','a_decidir')")  # 2
    return c


def gasto(con, i, valor, nome, data="2026-10-16", conta=1, natureza="caixa+custo", status="posted"):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) values (?,?,?,?,?,?,?)",
                (conta, f"g{i}", data, -valor, nome, natureza, status))


def comp(con, id_, venc, estado, valor, pago_em=None):
    con.execute("insert into compromisso(id, origem, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, estado, forma, dados) values (?,?,?,?,?,?,?,?,?,?)",
                (id_, "linha", id_.title(), venc, venc, valor, "valores_do_mes", estado, "", json.dumps({"pago_em": pago_em} if pago_em else {})))


def test_dia_sem_nada_diz_so_isso(con):
    assert montar(con, HOJE) == [SEM_MOVIMENTO]


def test_gastos_do_dia_total_e_tres_maiores_agrupados_por_nome(con):
    for i, (v, n) in enumerate([(5000, "Padaria"), (3000, "Padaria"), (12000, "Mercado"), (900, "Café"), (20000, "Escola"), (700, "Banca")]):
        gasto(con, i, v, n)
    gasto(con, 90, 99999, "Ontem", data="2026-10-15")
    gasto(con, 91, 88888, "Conta nao liberada", conta=2)
    gasto(con, 92, 77777, "Pendente", status="pending")
    gasto(con, 93, 66666, "Transferencia", natureza="caixa")
    t = "\n".join(montar(con, HOJE))
    assert "• Gastos: R$ 416,00 em 6 lançamento(s): Escola R$ 200,00; Mercado R$ 120,00; Padaria R$ 80,00" in t
    assert "Ontem" not in t and "nao liberada" not in t and "Pendente" not in t and "Transferencia" not in t


def test_pagas_hoje_e_atrasadas(con):
    comp(con, "luz", "2026-10-10", "pago", 30000, pago_em="2026-10-16T09:00:00")
    comp(con, "agua", "2026-10-09", "pago", 9999, pago_em="2026-10-09T09:00:00")  # paga em outro dia: não conta
    comp(con, "iptu", "2026-10-12", "atrasado", 90000)
    t = "\n".join(montar(con, HOJE))
    assert "• Pagas hoje: 1 (R$ 300,00)" in t and "• ⚠️ Atrasadas: 1 (R$ 900,00)" in t


def test_so_atrasada_ja_conta_como_movimento(con):
    comp(con, "iptu", "2026-10-12", "atrasado", 90000)
    t = montar(con, HOJE)
    assert t[0].startswith("🌙") and "Gastos: R$ 0,00 em 0 lançamento(s)" in t[1] and len(t) <= 5
