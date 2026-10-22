"""Evals de mensagens (EV3): cenário fixo -> texto exato guardado em `golden/`, mais regras que valem para QUALQUER mensagem.
Mudou o texto de propósito? Rode `EVALS_ATUALIZAR=1 pytest tests/evals` e leia o diff dos arquivos antes de commitar."""
import datetime as dt
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.agenda_financeira import montar

GOLDEN = Path(__file__).parent / "golden"
MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 20, 7, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))  # terça-feira
HOJE = AGORA.date()


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    c = conectar(tmp_path_factory.mktemp("evals") / "e.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b1','C6','BANK','C6 BANK','sim')")
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values ('b2','Itau','BANK','itau','sim')")
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (1, '2026-10-20T06:05:00', 2500000)")
    c.execute("insert into saldo(conta_id, em, saldo_centavos) values (2, '2026-10-20T06:05:00', 180000)")
    for id_, venc, estado, valor, fonte in [("escola", "2026-10-19", "aberto", 320000, "valores_do_mes"), ("condominio", "2026-10-20", "aberto", 118050, "valores_do_mes"),
                                            ("internet", "2026-10-21", "previsto", 19900, "ultimo"), ("vivo", "2026-10-22", "debito_automatico", 6400, "padrao"),
                                            ("seguro", "2026-10-28", "aberto", 450000, "valores_do_mes"), ("iptu", "2026-11-05", "aberto", 900000, "valores_do_mes")]:
        c.execute("insert into compromisso(id, origem, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, estado, forma) values (?,?,?,?,?,?,?,?,?)",
                  (id_, "linha", id_.title(), venc, venc, valor, fonte, estado, ""))
    for i, m in enumerate(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]):  # cliente que paga todo dia 7 e não pagou em outubro
        c.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, natureza, status) "
                  "values (1,?,?,1020800,'Pix recebido de CLIENTE EXEMPLO LTDA','caixa','posted')", (f"e{i}", f"{m}-07"))
    return c


def conferir_golden(nome: str, texto: str) -> None:
    arq = GOLDEN / f"{nome}.txt"
    if os.environ.get("EVALS_ATUALIZAR"):
        arq.write_text(texto + "\n", encoding="utf-8")
    assert arq.exists(), f"sem golden {arq.name}: rode com EVALS_ATUALIZAR=1"
    assert texto + "\n" == arq.read_text(encoding="utf-8"), f"mensagem '{nome}' mudou; confira o diff de {arq}"


MENSAGENS = {
    "agenda_diaria": lambda con: "\n".join(montar(con, AGORA)),
    "agenda_semanal": lambda con: "\n".join(montar(con, AGORA, dias=30, semanal=True)),
}


@pytest.mark.parametrize("nome", sorted(MENSAGENS))
def test_mensagem_igual_ao_golden(con, nome):
    conferir_golden(nome, MENSAGENS[nome](con))


@pytest.mark.parametrize("nome", sorted(MENSAGENS))
def test_regras_de_toda_mensagem(con, nome):
    t = MENSAGENS[nome](con)
    assert t.strip(), "mensagem vazia"
    assert len(t.splitlines()) <= 25, "mensagem longa demais para o celular"
    assert not re.search(r"\bnan\b|\bNone\b|\binf\b|\{|\}|\btraceback\b", t, re.I), "vazamento de valor interno"
    assert not re.search(r"R\$ ?-?\d+\.\d{2}\b", t), "dinheiro fora do formato brasileiro (R$ 1.234,56)"
    assert not re.search(r"\b\d{9,}\b", t), "número longo (conta, CPF ou token) não pertence à mensagem"
