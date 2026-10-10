import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.ingestao import ingerir
from gabi.db import conectar, migrar
from gabi.fontes.paperless import Paperless
from tests.cobrar.paperless_falso import PaperlessFalso

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 10)

PIX = """Comprovante de Pix
Valor: R$ 150,00
Data: 06/10/2026
Dados de quem recebeu
Nome: Maria Silva
CPF/CNPJ: 11.222.333/0001-81
Chave Pix: maria@exemplo.com
Dados de quem pagou
Nome: Ricardo
"""
SEM_VALOR = "Comprovante de Pix\nDados de quem recebeu\nNome: Fulano\n"
OUTRO = "Contrato de prestação de serviços entre as partes"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('b1','Itau','BANK','sim')")
    return c


def _pl(docs):
    falso = PaperlessFalso(docs=docs)
    return Paperless("http://p", "tok", http=falso), falso


def _doc(i, texto, criado="2026-10-06T10:00:00-03:00"):
    return {"id": i, "content": texto, "created": criado, "tags": []}


def test_le_valor_data_e_cnpj_do_comprovante(con):
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, status) values (1,'l1','2026-10-06',-15000,'PIX MARIA','posted')")
    pl, _ = _pl([_doc(7, PIX)])
    r = ingerir(con, pl, HOJE)
    assert (r.lidos, r.novos, r.sem_valor) == (1, 1, 0)
    c = con.execute("select * from comprovante where paperless_id=7").fetchone()
    assert (c["valor_centavos"], c["data"]) == (15000, "2026-10-06")
    assert con.execute("select count(*) from comprovante_vinculo where estado='proposto'").fetchone()[0] == 1


def test_ingestao_e_idempotente(con):
    pl, falso = _pl([_doc(7, PIX)])
    ingerir(con, pl, HOJE)
    r = ingerir(con, pl, HOJE)
    assert r.novos == 0
    assert con.execute("select count(*) from comprovante").fetchone()[0] == 1


def test_documento_sem_valor_nao_vira_comprovante(con):
    pl, _ = _pl([_doc(8, SEM_VALOR), _doc(9, OUTRO)])
    r = ingerir(con, pl, HOJE)
    assert (r.novos, r.sem_valor) == (0, 1)
    assert con.execute("select count(*) from comprovante").fetchone()[0] == 0


def test_etiqueta_so_acrescenta_gabi_comprovante(con):
    pl, falso = _pl([_doc(7, PIX)])
    ingerir(con, pl, HOJE)
    assert "gabi:comprovante" in falso.tags
    assert not any(m == "DELETE" for m, *_ in falso.chamadas)


def test_sem_data_no_texto_usa_a_data_de_criacao_do_documento(con):
    pl, _ = _pl([_doc(7, PIX.replace("Data: 06/10/2026\n", ""), criado="2026-10-05T09:00:00-03:00")])
    ingerir(con, pl, HOJE)
    assert con.execute("select data from comprovante").fetchone()[0] == "2026-10-05"
