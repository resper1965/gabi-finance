import datetime as dt
import json
import re
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import Orcamento
from gabi.familia.saude import abrir_saude
from gabi.fontes.paperless import Paperless
from gabi.reembolso_saude import rodada
from tests.cobrar.paperless_falso import PaperlessFalso

CHAVE = bytes(range(32))
AGORA = dt.datetime(2026, 10, 16, 15, 0, tzinfo=dt.timezone.utc)  # 12:00 em Brasília (sexta)
MIGR = Path(__file__).parent.parent.parent / "migrations"
TAGS = {"gabi:saude-reembolso": 1, "reembolso-a-pedir": 2, "reembolso-pedido": 3, "reembolso-recebido": 4}
# nomes e valores que NUNCA podem aparecer fora do cofre
SEGREDOS = ("Bia Souza", "Dra. Ana Lima", "300.00", "CRM 123", "pediatria", "12.345.678/0001-90")


class Falso(PaperlessFalso):
    """Acrescenta o filtro por tipo de documento (o falso original só entende tags__id__all)."""

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        m = re.search(r"document_type__name__iexact=([^&]+)", url)
        if metodo == "GET" and "/api/documents/?" in url and m:
            from urllib.parse import unquote
            nome = unquote(m.group(1)).lower()
            itens = [d for d in self.docs.values() if (d.get("tipo_nome") or "").lower() == nome]
            self.chamadas.append((metodo, url, corpo, ""))
            return 200, {"count": len(itens), "next": None, "results": itens}
        return super().__call__(metodo, url, corpo, cabecalhos)


class Modelo:
    """Responde pelo marcador que estiver no texto do documento (ex.: 'DOC-nf1'); `respostas` mapeia marcador -> dict (ou texto cru)."""

    def __init__(self, respostas, erro=None):
        self.respostas, self.erro, self.chamadas = respostas, erro, 0

    def completar(self, prompt, *, forte):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        for marca, r in self.respostas.items():
            if marca in prompt:
                return (r if isinstance(r, str) else json.dumps(r)), 0.001
        return "{}", 0.001


def pista(documento="nf", caso="consulta", **kw):
    base = {"documento": documento, "caso": caso, "paciente": "Bia Souza", "prestador": "Dra. Ana Lima", "data": "2026-10-03", "valor": 300,
            "doc_prestador": "12.345.678/0001-90", "conselho": "CRM 123", "especialidade": "pediatria", "confianca": 0.9}
    base.update(kw)
    return base


def doc(i, marca, tags=(1,), criado="2026-10-03", adicionado="2026-10-04T10:00:00-03:00", **kw):
    return {"id": i, "title": f"doc {i}", "content": f"texto do documento {marca}", "tags": list(tags), "created": criado, "added": adicionado, **kw}


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGR)
    return c


@pytest.fixture
def arq(tmp_path):
    return tmp_path / "s.enc"


def sistema(docs):
    srv = Falso(docs=docs, tags=dict(TAGS))
    return Paperless("http://p", "tok", http=srv), srv


def rodar(con, arq, paperless, modelo=None, agora=AGORA, orc=None):
    return rodada.rodar(con, lambda: abrir_saude(arq, CHAVE), paperless, modelo, orc or Orcamento(1, 10), agora)


def cofre_docs(arq):
    from gabi.reembolso_saude import cofre
    with abrir_saude(arq, CHAVE) as s:
        return cofre.docs(s)


def avisos(con, tipo=None):
    q = "select tipo, payload from aviso" + (" where tipo=?" if tipo else "")
    return [(r["tipo"], json.loads(r["payload"])) for r in con.execute(q, (tipo,) if tipo else ())]


def dump_banco(con) -> str:
    """Tudo que há no gabi.db das tabelas e dos avisos do reembolso, como texto."""
    saida = []
    for t in ("reembolso_saude_doc", "reembolso_saude_dossie", "reembolso_saude_acao", "aviso", "rodada", "custo_modelo"):
        saida += [str(tuple(r)) for r in con.execute(f"select * from {t}")]
    return "\n".join(saida)
