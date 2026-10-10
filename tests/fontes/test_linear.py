import json

import pytest

from gabi.fontes.linear import ErroLinear, Linear

RESP = {"data": {"issues": {"nodes": [
    {"id": "a1", "identifier": "ION-12", "title": "Entregar laudo", "dueDate": "2026-10-20", "updatedAt": "2026-10-09T10:00:00.000Z",
     "state": {"name": "In Progress", "type": "started"}, "project": {"name": "nCommand"}, "assignee": {"name": "Ricardo"}},
    {"id": "a2", "identifier": "ION-13", "title": "Sem prazo", "dueDate": None, "updatedAt": "2026-10-09T11:00:00.000Z",
     "state": {"name": "Todo", "type": "unstarted"}, "project": None, "assignee": None}],
    "pageInfo": {"hasNextPage": False, "endCursor": None}}}}


class Http:
    def __init__(self, status=200, resp=RESP):
        self.status, self.resp, self.chamadas = status, resp, []

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, url, corpo, cabecalhos))
        return self.status, self.resp


def test_entregas_abertas_normalizadas():
    es = Linear(lambda: "tok", http=Http()).entregas_abertas()
    assert es[0] == {"externo_id": "a1", "identificador": "ION-12", "titulo": "Entregar laudo", "projeto": "nCommand", "responsavel": "Ricardo",
                     "prazo": "2026-10-20", "estado": "In Progress", "atualizado_em": "2026-10-09T10:00:00.000Z"}
    assert es[1]["projeto"] is None and es[1]["prazo"] is None


def test_linear_somente_leitura():
    h = Http()
    c = Linear(lambda: "tok", http=h)
    c.entregas_abertas()
    assert all("mutation" not in (corpo or {}).get("query", "").lower() for _, _, corpo, _ in h.chamadas)
    assert not [n for n in dir(c) if not n.startswith("_") and any(p in n for p in ("criar", "atualizar", "concluir", "apagar", "delete", "update", "create"))]
    assert h.chamadas[0][0] == "POST" and h.chamadas[0][3]["Authorization"] == "tok"  # chave pessoal da Linear vai crua, sem Bearer


def test_erro_http_e_erro_graphql_levantam_com_status():
    with pytest.raises(ErroLinear, match="-> 401"):
        Linear(lambda: "x", http=Http(401, {"errors": [{"message": "auth"}]})).entregas_abertas()
    with pytest.raises(ErroLinear, match="graphql"):
        Linear(lambda: "x", http=Http(200, {"errors": [{"message": "ruim"}]})).entregas_abertas()


def test_pagina_ate_acabar():
    p1 = {"data": {"issues": {"nodes": RESP["data"]["issues"]["nodes"][:1], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}}
    p2 = {"data": {"issues": {"nodes": RESP["data"]["issues"]["nodes"][1:], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
    respostas = iter([p1, p2])
    h = Http()
    h.__call__ = None
    chamadas = []

    def http(metodo, url, corpo=None, cabecalhos=None):
        chamadas.append(corpo)
        return 200, next(respostas)
    assert len(Linear(lambda: "x", http=http).entregas_abertas()) == 2
    assert chamadas[1]["variables"]["depois"] == "c1"
