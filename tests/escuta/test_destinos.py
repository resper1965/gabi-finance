import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.destinos import DestinosReais
from gabi.fontes.paperless import Paperless
from tests.cobrar.paperless_falso import PaperlessFalso

MIGR = Path(__file__).parent.parent.parent / "migrations"
N = "+5511912345678"
SEGREDO = "TEXTO-DE-SAUDE-SECRETO-777"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into pessoa(id, nome, dados) values ('p1','Fulana', ?)",
              (json.dumps({"canais": [f"whatsapp:{N}"], "pode_pedir": True}),))
    return c


@pytest.fixture
def srv():
    return PaperlessFalso()


@pytest.fixture
def d(srv):
    return DestinosReais(Paperless("http://p", "tok", http=srv))


def _msg(texto="oi", anexo=None):
    return {"id": 1, "id_externo": "m1", "de": N, "texto": texto, "anexo_caminho": str(anexo) if anexo else None}


def _avisos(con, tipo):
    return [json.loads(r["payload"]) for r in con.execute("select payload from aviso where tipo=?", (tipo,))]


def test_pedido_vira_registro_pendente_e_nao_diz_que_pagou(con, d):
    d.pedido(con, "p1", N, _msg("paga a Maria 100"), {"favorecido": "Maria", "motivo": "diarista", "valor": 100, "vence": "2026-10-20", "chave_ou_linha": "maria@x.com"})
    p = con.execute("select * from pedido").fetchone()
    assert p["estado"] == "pendente" and p["valor_centavos"] == 10000 and p["canal"] == "whatsapp"
    assert p["solicitante_ident"] == f"whatsapp:{N}" and p["mensagem_original"] == "paga a Maria 100"
    assert p["pix_chave"] == "maria@x.com" and p["linha_digitavel"] is None and p["vencimento"] == "2026-10-20"
    assert "Maria" in p["descricao"] and "diarista" in p["descricao"] and p["para_quem_id"] is None


def test_pedido_linha_digitavel_e_distinguida_da_chave_pix(con, d):
    linha = "23793.38128 60000.000003 00000.000400 1 84340000012345"
    d.pedido(con, "p1", N, _msg(), {"valor": 123.45, "chave_ou_linha": linha})
    p = con.execute("select * from pedido").fetchone()
    assert p["linha_digitavel"] == linha and p["pix_chave"] is None


def test_pedido_sem_valor_propaga_value_error_e_nao_grava(con, d):
    with pytest.raises(ValueError):
        d.pedido(con, "p1", N, _msg(), {"favorecido": "Maria"})
    assert con.execute("select count(*) from pedido").fetchone()[0] == 0


def test_pedido_com_anexo_vai_ao_paperless_com_etiqueta(con, d, srv, tmp_path):
    arq = tmp_path / "boleto.pdf"
    arq.write_bytes(b"%PDF-boleto")
    d.pedido(con, "p1", N, _msg(anexo=arq), {"valor": 50})
    corpo = srv.enviados[0][0]
    assert b"%PDF-boleto" in corpo and "gabi:entrada-whatsapp" in srv.tags and arq.exists()
    assert con.execute("select count(*) from pedido").fetchone()[0] == 1


def test_saude_envia_anexo_com_etiqueta_e_nao_apaga_nada(con, d, srv, tmp_path):
    arq = tmp_path / "exame.pdf"
    arq.write_bytes(b"%PDF-exame")
    d.saude(con, _msg(SEGREDO, arq), {"x": SEGREDO})
    corpo, _ = srv.enviados[0]
    assert b"%PDF-exame" in corpo and b'filename="exame.pdf"' in corpo and "gabi:saude-exame" in srv.tags
    assert arq.exists()  # quem apaga é o processar
    assert _avisos(con, "escuta_saude") == []


def _tudo(con):
    for (t,) in con.execute("select name from sqlite_master where type='table'").fetchall():
        for r in con.execute(f'select * from "{t}"'):
            yield t, [str(v) for v in tuple(r)]


def test_saude_nao_grava_texto_no_banco(con, d, tmp_path):
    arq = tmp_path / "exame.pdf"
    arq.write_bytes(b"x")
    d.saude(con, {**_msg(SEGREDO, arq)}, {"resumo": SEGREDO})
    d.saude(con, _msg(SEGREDO), {"resumo": SEGREDO})
    assert [t for t, vs in _tudo(con) if any(SEGREDO in v for v in vs)] == []


def test_saude_sem_anexo_apenas_avisa_sem_texto(con, d, srv):
    con.execute("insert into escuta_remetente(numero, estado, vista_em, qtd, nome) values (?, 'aprovado', 'x', 1, 'Fulana')", (N,))
    d.saude(con, _msg(SEGREDO), {"resumo": SEGREDO})
    assert _avisos(con, "escuta_saude") == [{"numero": N, "nome": "Fulana"}] and srv.enviados == []


def test_saude_sem_anexo_nome_desconhecido_vira_none(con, d):
    d.saude(con, {**_msg(SEGREDO), "de": "+5500000000"}, {})
    assert _avisos(con, "escuta_saude") == [{"numero": "+5500000000", "nome": None}]


def test_crise_aviso_so_com_numero_e_nome(con, d):
    d.crise(con, N, "Fulana")
    assert _avisos(con, "escuta_atencao") == [{"numero": N, "nome": "Fulana"}]


def test_crise_deduplica_por_numero_por_hora(con, d):
    d.crise(con, N, "Fulana")
    d.crise(con, N, "Fulana")
    d.crise(con, "+5599", None)
    assert len(_avisos(con, "escuta_atencao")) == 2
    con.execute("update aviso set criado_em='2020-01-01T00:00:00+00:00' where tipo='escuta_atencao'")  # há muito tempo
    d.crise(con, N, "Fulana")
    assert len(_avisos(con, "escuta_atencao")) == 3


def test_documento_envia_com_etiqueta_e_propaga_erro(con, d, srv, tmp_path):
    arq = tmp_path / "nf.pdf"
    arq.write_bytes(b"%PDF-nf")
    d.documento(con, _msg(anexo=arq))
    assert b"%PDF-nf" in srv.enviados[0][0] and "gabi:entrada-whatsapp" in srv.tags

    def quebrado(*a, **k):
        return 500, {}

    ruim = DestinosReais(Paperless("http://p", "tok", http=quebrado))
    with pytest.raises(Exception):
        ruim.documento(con, _msg(anexo=arq))
    assert arq.exists()
