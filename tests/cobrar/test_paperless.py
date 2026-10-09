import inspect

import pytest

from gabi.cobrar.extrator import achar_cnpj, achar_codigo
from gabi.fontes import paperless as modulo
from gabi.fontes.paperless import Paperless
from tests.cobrar.paperless_falso import PaperlessFalso


def _cli(**kw):
    srv = PaperlessFalso(**kw)
    return Paperless("http://p", "tok-gabi", http=srv), srv


def test_cliente_nao_expoe_metodo_de_exclusao():
    nomes = [n for n, _ in inspect.getmembers(Paperless, inspect.isfunction)]
    assert not [n for n in nomes if n.lstrip("_").startswith(("delete", "remove", "destroy", "apagar", "excluir"))]


def test_o_codigo_nunca_emite_delete():
    assert '"DELETE"' not in inspect.getsource(modulo)  # o módulo nem sabe montar uma chamada DELETE


def test_docs_pagina_ate_o_fim_e_manda_o_token():
    cli, srv = _cli(docs=[{"id": i, "title": f"d{i}", "tags": []} for i in range(1, 6)])
    assert [d["id"] for d in cli.docs(page_size=2)] == [1, 2, 3, 4, 5]
    assert all(c[3] == "Token tok-gabi" for c in srv.chamadas)


def test_baixar_devolve_os_bytes():
    cli, _ = _cli(docs=[{"id": 3, "title": "x", "tags": []}])
    assert cli.baixar(3) == b"%PDF-falso-3"


def test_etiquetar_nunca_remove_nem_move():
    cli, srv = _cli(docs=[{"id": 1, "title": "x", "tags": [1, 2]}], tags={"pago": 1, "ness": 2})
    cli.etiquetar(1, ["gabi:reembolso"])
    novas = srv.docs[1]["tags"]
    assert {1, 2} <= set(novas) and len(novas) == 3  # as antigas ficam; entra a nova


def test_etiquetar_so_aceita_etiqueta_gabi():
    cli, srv = _cli(docs=[{"id": 1, "title": "x", "tags": [1]}], tags={"pago": 1})
    with pytest.raises(ValueError):
        cli.etiquetar(1, ["pago-2"])
    assert srv.docs[1]["tags"] == [1] and not [c for c in srv.chamadas if c[0] == "PATCH"]


def test_etiquetar_reaproveita_a_etiqueta_existente():
    cli, srv = _cli(docs=[{"id": 1, "title": "x", "tags": []}], tags={"gabi:reembolso": 9})
    cli.etiquetar(1, ["gabi:reembolso"])
    assert srv.docs[1]["tags"] == [9] and not [c for c in srv.chamadas if c[0] == "POST"]


def test_campos_le_cpf_valor_vencimento_e_pessoa():
    cli, _ = _cli(docs=[{"id": 1, "title": "x", "tags": [], "custom_fields": [
        {"field": 11, "value": "123.456.789-09"}, {"field": 12, "value": "R$231.00"}, {"field": 13, "value": "2026-10-20"}]}],
        campos={"CPF": 11, "valor": 12, "vencimento": 13, "pessoa": 14})
    assert cli.campos(1) == {"CPF": "123.456.789-09", "valor": "R$231.00", "vencimento": "2026-10-20", "pessoa": None}


def test_usuario_gabi_sem_permissao_de_apagar():
    srv = PaperlessFalso()
    cli = Paperless("http://p", "tok-gabi", http=srv)
    token = cli.preparar_usuario("tok-admin")
    u = srv.usuarios["gabi"]
    assert u["user_permissions"] and not [p for p in u["user_permissions"] if p.startswith("delete_")]
    assert "view_document" in u["user_permissions"] and "change_document" in u["user_permissions"]
    assert token == "tok-gabi-falso"


def test_preparar_usuario_usa_o_token_admin_so_nas_chamadas_dele_e_nao_o_guarda():
    srv = PaperlessFalso()
    cli = Paperless("http://p", "tok-gabi", http=srv)
    cli.preparar_usuario("tok-admin")
    assert any(c[3] == "Token tok-admin" for c in srv.chamadas)
    assert "tok-admin" not in repr(vars(cli)) and cli.token == "tok-gabi"
    assert {"CPF", "valor", "vencimento", "pessoa"} <= set(srv.campos)  # cria os campos personalizados


def test_achar_codigo_pix_ganha_da_linha_digitavel():
    pix = "00020126580014BR.GOV.BCB.PIX0136123e4567-e89b-12d3-a456-4266141740005204000053039865406123.455802BR5913FULANO DE TAL6009SAO PAULO62070503***630465DC"
    linha = "23793.38128 60000.000003 00000.000400 1 84340000012345"
    r = achar_codigo(f"{linha} {pix}", __import__("datetime").date(2026, 10, 8))
    assert r["tipo"] == "pix"


def test_cnpj_so_com_digitos_verificadores():
    assert achar_cnpj("CNPJ 11.222.333/0001-81") == "11222333000181"
    assert achar_cnpj("CNPJ 11.222.333/0001-82") is None
