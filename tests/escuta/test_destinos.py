import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.escuta.destinos import DestinosReais
from gabi.fontes.paperless import ErroPaperless, Paperless
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
def d(srv, tmp_path):
    return DestinosReais(Paperless("http://p", "tok", http=srv), spool=tmp_path)


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
    assert con.execute("select anexo_paperless_id from pedido").fetchone()[0] is None  # o Paperless devolve UUID de tarefa; vínculo adiado


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
    d.crise(con, N, "Fulana", "2026-10-11T10:00:00")
    d.crise(con, N, "Fulana", "2026-10-11T10:59:00")  # 59 min: suprimido
    d.crise(con, "+5599", None, "2026-10-11T10:59:00")  # outro número
    assert len(_avisos(con, "escuta_atencao")) == 2
    d.crise(con, N, "Fulana", "2026-10-11T11:01:00")  # 61 min depois do primeiro: novo aviso
    assert len(_avisos(con, "escuta_atencao")) == 3
    assert con.execute("select criado_em from aviso where tipo='escuta_atencao' order by id desc limit 1").fetchone()[0] == "2026-10-11T11:01:00"


def test_crise_sem_agora_usa_relogio_utc(con, d):
    d.crise(con, N, "Fulana")
    d.crise(con, N, "Fulana")
    assert len(_avisos(con, "escuta_atencao")) == 1


def test_documento_envia_com_etiqueta_e_propaga_erro(con, d, srv, tmp_path):
    arq = tmp_path / "nf.pdf"
    arq.write_bytes(b"%PDF-nf")
    d.documento(con, _msg(anexo=arq))
    assert b"%PDF-nf" in srv.enviados[0][0] and "gabi:entrada-whatsapp" in srv.tags

    def quebrado(metodo, url, corpo=None, cab=None):
        if "post_document" in url:
            return 500, {"detail": "x"}
        return srv(metodo, url, corpo, cab)

    ruim = DestinosReais(Paperless("http://p", "tok", http=quebrado), spool=tmp_path)
    with pytest.raises(ErroPaperless, match="post_document"):
        ruim.documento(con, _msg(anexo=arq))
    assert arq.exists()


def test_pedido_valor_passa_sem_converter_para_texto(con, srv, tmp_path):
    vistos = {}

    def registrar(con, **kw):
        vistos.update(kw)

    DestinosReais(Paperless("http://p", "t", http=srv), registrar, spool=tmp_path).pedido(con, "p1", N, _msg(), {"valor": 1.234})
    assert vistos["valor"] == 1.234 and isinstance(vistos["valor"], float)


def test_pedido_dentro_do_spool_e_fora(con, srv, tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    chamadas = []
    d = DestinosReais(Paperless("http://p", "t", http=srv), lambda con, **kw: chamadas.append(kw), spool=spool)
    fora = tmp_path / "fora.env"
    fora.write_text("PAPERLESS_TOKEN=abc")
    for caminho in (fora, spool / ".." / "fora.env"):
        with pytest.raises(RuntimeError):
            d.pedido(con, "p1", N, _msg(anexo=caminho), {"valor": 10})
    assert chamadas == [] and srv.enviados == [] and srv.chamadas == []


def test_destinos_diretos_recusam_caminho_fora_do_spool(con, srv, tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    fora = tmp_path / "fora.env"
    fora.write_text("segredo")
    d = DestinosReais(Paperless("http://p", "t", http=srv), spool=spool)
    for chamada in (lambda: d.documento(con, _msg(anexo=fora)), lambda: d.saude(con, _msg(anexo=fora), {})):
        with pytest.raises(RuntimeError):
            chamada()
    assert srv.enviados == []


def test_symlink_dentro_do_spool_apontando_para_fora_e_recusado(con, srv, tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    fora = tmp_path / "fora.env"
    fora.write_text("segredo")
    elo = spool / "elo.pdf"
    elo.symlink_to(fora)
    d = DestinosReais(Paperless("http://p", "t", http=srv), spool=spool)
    with pytest.raises(RuntimeError):
        d.documento(con, _msg(anexo=elo))
    assert srv.enviados == []


def test_diretorio_e_spool_none_sao_recusados(con, srv, tmp_path):
    spool = tmp_path / "spool"
    (spool / "pasta").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        DestinosReais(Paperless("http://p", "t", http=srv), spool=spool).documento(con, _msg(anexo=spool / "pasta"))
    arq = spool / "a.pdf"
    arq.write_bytes(b"x")
    with pytest.raises(RuntimeError):
        DestinosReais(Paperless("http://p", "t", http=srv)).documento(con, _msg(anexo=arq))


def test_teto_de_tamanho_logo_abaixo_passa_e_acima_recusa(con, srv, tmp_path, monkeypatch):
    d = DestinosReais(Paperless("http://p", "t", http=srv), spool=tmp_path, anexo_max_bytes=10)
    ok = tmp_path / "ok.bin"
    ok.write_bytes(b"x" * 10)
    d.documento(con, _msg(anexo=ok))
    assert len(srv.enviados) == 1
    grande = tmp_path / "grande.bin"
    grande.write_bytes(b"x" * 11)
    lidos = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda f, *a, **k: (lidos.append(str(f)), real_open(f, *a, **k))[1])
    with pytest.raises(RuntimeError):
        d.documento(con, _msg(anexo=grande))
    assert not [x for x in lidos if x.endswith("grande.bin")] and len(srv.enviados) == 1 and grande.exists()


def test_teto_padrao_e_25_mib(srv):
    assert DestinosReais(Paperless("http://p", "t", http=srv))._max == 25 * 1024 * 1024


def test_quando_sem_offset_vale_brasilia():
    from gabi.escuta.destinos import _quando
    assert _quando("2026-10-11T09:00:00") == _quando("2026-10-11T12:00:00+00:00")
