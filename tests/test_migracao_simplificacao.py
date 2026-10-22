"""Migração 0075 (ADR-023): só tabelas VAZIAS saem; as legadas com dado ficam intactas; a memória perde o índice FTS e continua gravável."""
import shutil
from pathlib import Path

from gabi.db import conectar, migrar

MIGR = Path(__file__).parent.parent / "migrations"
SAEM = ["escuta_msg", "escuta_grupo", "exame_doc", "reembolso_saude_acao", "reembolso_saude_doc", "reembolso_saude_dossie", "edicao_externa",
        "liberacao_sensivel", "item_email", "item_frente", "frente", "evento", "tarefa", "entrega", "regra_expurgo", "cobranca_item", "cobranca",
        "comprovante_vinculo", "comprovante", "reembolso_baixa", "reembolso_item", "reembolso", "lote_nibo_item", "lote_nibo", "pedido", "setup_passo",
        "memoria_fts"]


def _tabelas(con) -> set[str]:
    return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}


def test_0075_tira_as_vazias_e_preserva_as_legadas(tmp_path):
    antes = tmp_path / "antes"
    antes.mkdir()
    for arq in sorted(MIGR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if arq.name < "0075":
            shutil.copy(arq, antes / arq.name)
    con = conectar(tmp_path / "g.db")
    migrar(con, antes)
    assert set(SAEM) <= _tabelas(con)
    con.execute("insert into escuta_remetente(numero, estado, vista_em, qtd) values ('+5511900000000','pendente','2026-10-01',1)")
    con.execute("insert into caixa_email(endereco, provedor, estado) values ('a@b.c','graph','sim')")
    con.execute("insert into memoria(chave, tipo, texto) values ('k','nota','texto antigo')")
    migrar(con, MIGR)
    assert not set(SAEM) & _tabelas(con)
    assert con.execute("select count(*) from escuta_remetente").fetchone()[0] == 1
    assert con.execute("select count(*) from caixa_email").fetchone()[0] == 1
    con.execute("insert into memoria(chave, tipo, texto) values ('k2','nota','texto novo')")  # sem os gatilhos do FTS
    assert [r[0] for r in con.execute("select texto from memoria order by id")] == ["texto antigo", "texto novo"]
    assert not con.execute("select name from sqlite_master where type='trigger' and name like 'memoria_%'").fetchall()
