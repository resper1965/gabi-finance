import re

from gabi.fontes.nibo_escrita import NiboEscrita


class Http:
    def __init__(self, respostas=None):
        self.respostas, self.chamadas = respostas or {}, []

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, re.sub(r"^https://[^/]+/empresas/v1", "", url), corpo, cabecalhos))
        for padrao, resp in self.respostas.items():
            if re.search(padrao, url):
                return resp
        return 200, {"items": []}


def _nibo(respostas=None):
    h = Http(respostas)
    arquivos = []
    n = NiboEscrita("tok", http=h, http_arquivo=lambda url, nome, conteudo, cab: (arquivos.append((url, nome, conteudo, cab)) or (200, [{"fileId": "f1"}])))
    return n, h, arquivos


def test_criar_agendamento_posta_na_rota_de_debito_com_reference_e_valor_em_reais():
    n, h, _ = _nibo({"schedules/debit": (200, {"scheduleId": "s9"})})
    sid = n.criar_agendamento_debito(stakeholder_id="soc", valor_centavos=12345, data="2026-10-01", category_id="cat", descricao="LOJA", reference="gabi:7")
    assert sid == "s9"
    metodo, rota, corpo, cab = h.chamadas[0]
    assert (metodo, rota) == ("POST", "/schedules/debit/FormatType=json") and cab == {"ApiToken": "tok"}
    assert corpo == {"stakeholderId": "soc", "value": 123.45, "dueDate": "2026-10-01", "scheduleDate": "2026-10-01", "accrualDate": "2026-10-01",
                     "categoryId": "cat", "description": "LOJA", "reference": "gabi:7"}


def test_anexar_envia_o_arquivo_e_depois_o_attach():
    n, h, arquivos = _nibo({"files/attach": (204, None)})
    n.anexar_arquivo("s9", "c.pdf", b"%PDF")
    assert arquivos[0][1:3] == ("c.pdf", b"%PDF") and arquivos[0][0].endswith("/files")
    assert h.chamadas[0][:3] == ("POST", "/schedules/debit/s9/files/attach", ["f1"])


def test_baixar_pagamento_posta_em_payments():
    n, h, _ = _nibo({"payments": (200, {})})
    n.baixar_pagamento("s9", account_id="c6pj", data="2026-10-12", valor_centavos=10000, identifier="gabi:baixa:5")
    assert h.chamadas[0][:3] == ("POST", "/schedules/debit/s9/payments", {"accountId": "c6pj", "date": "2026-10-12", "value": 100.0, "identifier": "gabi:baixa:5"})


def test_agendamento_por_reference_filtra_por_reference():
    n, h, _ = _nibo({"schedules": (200, {"items": [{"scheduleId": "s1"}]})})
    assert n.agendamento_por_reference("gabi:7") == {"scheduleId": "s1"}
    assert "reference%20eq%20%27gabi%3A7%27" in h.chamadas[0][1] or "reference+eq+%27gabi%3A7%27" in h.chamadas[0][1]


def test_o_cliente_de_escrita_nao_tem_exclusao_nem_edicao():
    nomes = [x for x in dir(NiboEscrita) if not x.startswith("_")]
    assert not [x for x in nomes if re.match(r"(delete|excluir|remover|atualizar|editar|cancelar|put|patch)", x)]
