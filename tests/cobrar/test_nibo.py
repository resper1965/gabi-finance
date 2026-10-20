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
    assert {"organizations", "contas", "agendamentos", "extrato", "nfse", "obter_arquivo", "agendamentos_a_receber", "socios", "clientes", "categorias"} <= set(nomes)


def test_nenhuma_rota_de_exclusao_no_codigo():
    """Chamadas de SAÍDA (urllib/requests). `@router.delete` é a exclusão lógica de cadastros da própria API, não conta."""
    achados = []
    for arq in RAIZ.rglob("*.py"):
        if "painel" in arq.parts or arq.name == "graph_ness_contatos.py":  # o único DELETE do código: apagar contato da ness, aprovado um a um (ADR-021; travado em test_graph_ness_contatos_escrita)
            continue
        for i, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<!router)\.delete\(|requests\.delete|[\"']DELETE[\"']|method\s*=\s*[\"']DELETE", linha) and "re.search" not in linha:
                achados.append(f"{arq.relative_to(RAIZ)}:{i}")
    assert achados == []


def test_nfse_ordena_por_createDate_e_filtra_com_offset():
    # o Nibo responde 500 para $orderby=emissionDate e para data sem offset (conferido com o token real em 09/10/2026)
    n, srv = _nibo(itens=[])
    list(n.nfse(dt.date(2026, 1, 1)))
    q = parse_qs(urlparse(srv.chamadas[0][1]).query)
    assert srv.chamadas[0][1].split("?")[0].endswith("/nfse")
    assert q["$orderby"] == ["createDate"] and unquote(q["$filter"][0]) == "createDate ge 2026-01-01T00:00:00Z"


def test_obter_arquivo_so_do_host_de_arquivos_do_nibo():
    chamadas = []

    def http_arquivo(url, cabecalhos):
        chamadas.append((url, cabecalhos))
        return 200, b"%PDF-1.4"
    n = Nibo("tok-nibo", http=NiboFalso(), http_download=http_arquivo)
    assert n.obter_arquivo("https://arquivos.nibo.com.br/download/abc") == b"%PDF-1.4"
    assert chamadas[0][1]["ApiToken"] == "tok-nibo"
    for ruim in ("https://evil.example/download/abc", "http://arquivos.nibo.com.br/download/abc", "https://arquivos.nibo.com.br.evil.example/x"):
        with pytest.raises(ErroNibo):
            n.obter_arquivo(ruim)
    assert len(chamadas) == 1  # a URL fora do host nunca chegou à rede (o token não vaza)


def test_obter_arquivo_status_de_erro_vira_erronibo():
    n = Nibo("t", http=NiboFalso(), http_download=lambda u, c: (404, b""))
    with pytest.raises(ErroNibo):
        n.obter_arquivo("https://arquivos.nibo.com.br/download/x")


def test_nfse_aceita_data_como_texto_iso_porque_a_ponte_so_leva_json():
    from gabi.fontes.ponte import _codificar
    assert _codificar([dt.date(2017, 1, 1)]) == ["2017-01-01"]
    n, srv = _nibo(itens=[])
    list(n.nfse("2017-01-01"))
    assert "createDate ge 2017-01-01T00:00:00Z" in unquote(parse_qs(urlparse(srv.chamadas[0][1]).query)["$filter"][0])


def test_nibo_escrita_herda_o_download_sem_colidir_com_o_envio_de_anexo():
    # a ponte usa NiboEscrita; ele tem o próprio gancho de envio (multipart) e não pode atropelar o de download
    from gabi.fontes.nibo_escrita import NiboEscrita
    n = NiboEscrita("tok", http=NiboFalso(), http_arquivo=lambda *a: (200, b"envio"))
    n._http_download = lambda url, cab: (200, b"%PDF-ok")
    assert n.obter_arquivo("https://arquivos.nibo.com.br/download/x") == b"%PDF-ok"
    sem_gancho = NiboEscrita("tok", http=NiboFalso(), http_arquivo=lambda *a: (200, b"envio"))
    assert sem_gancho._http_download is not sem_gancho._http_arquivo
