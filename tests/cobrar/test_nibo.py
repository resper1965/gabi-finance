import datetime as dt
import inspect
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from gabi.fontes import nibo as modulo
from gabi.fontes.nibo import ErroNibo, Nibo

RAIZ = Path(__file__).parent.parent.parent / "gabi"


class NiboFalso:
    def __init__(self, itens=None, status=200, corpo=None):
        self.itens, self.status, self.corpo = itens or [], status, corpo
        self.chamadas = []  # (metodo, url, cabecalhos)

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, url, cabecalhos or {}))
        if self.status != 200:
            return self.status, self.corpo
        q = parse_qs(urlparse(url).query)
        skip, top = int(q.get("$skip", ["0"])[0]), int(q.get("$top", ["500"])[0])
        return 200, {"count": len(self.itens), "items": self.itens[skip:skip + top]}


def _nibo(**kw):
    srv = NiboFalso(**kw)
    return Nibo("tok-nibo", http=srv), srv


def test_header_e_apitoken_nunca_authorization():
    n, srv = _nibo(itens=[{"id": 1}])
    n.organizations()
    cab = srv.chamadas[0][2]
    assert cab["ApiToken"] == "tok-nibo" and "Authorization" not in cab


def test_paginacao_odata_ate_500_com_orderby():
    n, srv = _nibo(itens=[{"scheduleId": str(i), "updateDate": "2026-10-01T00:00:00"} for i in range(1200)])
    todos = list(n.agendamentos(dt.datetime(2026, 1, 1), None))
    assert len(todos) == 1200
    skips = [int(parse_qs(urlparse(c[1]).query)["$skip"][0]) for c in srv.chamadas]
    assert skips == [0, 500, 1000]
    for _, url, _ in srv.chamadas:
        q = parse_qs(urlparse(url).query)
        assert q["$top"] == ["500"] and q["$orderby"] == ["updateDate"]


def test_incremental_por_updateDate_e_tipo():
    n, srv = _nibo(itens=[])
    list(n.agendamentos(dt.datetime(2026, 10, 1, 12, 30), "Debit"))
    filtro = unquote(parse_qs(urlparse(srv.chamadas[0][1]).query)["$filter"][0])
    assert "updateDate gt 2026-10-01T12:30:00" in filtro and "Debit" in filtro
    assert srv.chamadas[0][1].split("?")[0].endswith("/schedules")


def test_extrato_usa_a_view_statement_com_datas():
    n, srv = _nibo(itens=[{"entryId": "e1"}])
    assert n.extrato("acc1", dt.date(2026, 10, 1), dt.date(2026, 10, 8)) == [{"entryId": "e1"}]
    url = srv.chamadas[0][1]
    assert "/accounts/acc1/views/statement" in url and "startDate=2026-10-01" in url and "endDate=2026-10-08" in url


def test_erro_500_error_description_vira_ErroNibo():
    n, _ = _nibo(status=500, corpo={"error": "server_error", "error_description": "limite excedido"})
    with pytest.raises(ErroNibo, match="limite excedido"):
        n.organizations()


def test_erro_400_messageDetail_vira_ErroNibo_sem_o_token():
    n, _ = _nibo(status=400, corpo={"message": "inválido", "messageDetail": "campo X"})
    with pytest.raises(ErroNibo) as e:
        n.contas()
    assert "campo X" in str(e.value) and "tok-nibo" not in str(e.value)


def test_cliente_de_leitura_nao_tem_metodo_de_escrita():
    nomes = [n for n, _ in inspect.getmembers(Nibo, inspect.isfunction) if not n.startswith("_")]
    assert not [n for n in nomes if re.match(r"(criar|atualizar|editar|excluir|delete|remover|anexar|baixar|post|put|patch)", n)]
    assert {"organizations", "contas", "agendamentos", "extrato", "nfse", "socios", "clientes", "categorias"} <= set(nomes)


def test_nenhuma_rota_de_exclusao_no_codigo():
    """Chamadas de SAÍDA (urllib/requests). `@router.delete` é a exclusão lógica de cadastros da própria API, não conta."""
    achados = []
    for arq in RAIZ.rglob("*.py"):
        if "painel" in arq.parts:
            continue
        for i, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<!router)\.delete\(|requests\.delete|[\"']DELETE[\"']|method\s*=\s*[\"']DELETE", linha) and "re.search" not in linha:
                achados.append(f"{arq.relative_to(RAIZ)}:{i}")
    assert achados == []
