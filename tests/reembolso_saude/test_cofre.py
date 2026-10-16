import datetime as dt

import pytest

from gabi.familia.saude import abrir_saude
from gabi.reembolso_saude import cofre

CHAVE = bytes(range(32))


@pytest.fixture
def arq(tmp_path):
    return tmp_path / "s.enc"


def _doc(i=10, **kw):
    base = {"id": i, "documento": "nf", "caso": "consulta", "campos": {"paciente": "Bia", "prestador": "Dra. Ana", "valor": "300.00"},
            "data": dt.date(2026, 10, 3), "adicionado": dt.date(2026, 10, 4), "confianca": 0.9, "estado": "a_pedir"}
    base.update(kw)
    return base


def test_gravar_e_ler_documento_e_dossie(arq):
    with abrir_saude(arq, CHAVE) as s:
        d = cofre.gravar_doc(s, _doc())
        assert d == 1
        assert cofre.gravar_doc(s, _doc(11, campos={"paciente": "bia", "prestador": "ana"})) == 1  # mesmo dossiê (normalizado)
        assert cofre.gravar_doc(s, _doc(12, data=dt.date(2026, 9, 3))) == 2
    with abrir_saude(arq, CHAVE) as s:
        docs = cofre.docs(s)
        assert [x["id"] for x in docs] == [10, 11, 12] and docs[0]["data"] == dt.date(2026, 10, 3) and docs[0]["campos"]["prestador"] == "Dra. Ana"
        assert cofre.dossie(s, 2)["mes"] == "2026-09"


def test_regravar_documento_atualiza_sem_duplicar(arq):
    with abrir_saude(arq, CHAVE) as s:
        cofre.gravar_doc(s, _doc())
        cofre.gravar_doc(s, _doc(estado="pedido", pedido_em=dt.date(2026, 10, 9), protocolo="P1"))
        (d,) = cofre.docs(s)
        assert d["estado"] == "pedido" and d["pedido_em"] == dt.date(2026, 10, 9) and d["protocolo"] == "P1"


def test_avisos_do_dossie_persistem(arq):
    with abrir_saude(arq, CHAVE) as s:
        n = cofre.gravar_doc(s, _doc())
        assert cofre.avisos_do_dossie(s, n) == []
        cofre.gravar_avisos(s, n, ["abre"])
    with abrir_saude(arq, CHAVE) as s:
        assert cofre.avisos_do_dossie(s, 1) == ["abre"]


def test_nao_mexe_nas_tabelas_dos_exames(arq):
    with abrir_saude(arq, CHAVE) as s:
        cofre.gravar_doc(s, _doc())
        tabelas = {r[0] for r in s.con.execute("select name from sqlite_master where type='table'")}
    assert {"exame", "proposta_exame", "reembolso_doc", "reembolso_dossie"} <= tabelas
