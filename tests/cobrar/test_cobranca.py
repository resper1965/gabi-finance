import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.cobrar.cobranca import NaoPermitido, enviar, montar, texto_confirmacao
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")
    c.execute("insert into empresa(id, nome, relacao, dados) values ('ness','Ness','contratante', ?)", (json.dumps({"email_cobranca": "financeiro@ness.com.br"}),))
    c.execute("insert into empresa(id, nome, relacao) values ('ionic','IONIC','contratante')")  # sem e-mail cadastrado
    c.execute("insert into empresa(id, nome, relacao) values ('bekaa','Bekaa','pj_titular')")
    return c


def _l(con, i, data, valor, empresa="ness", desc="HOTEL X"):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, status) "
                       "values (1,?,?,?,?,?,?, 'posted')", (f"l{i}", data, valor, desc, desc, empresa)).lastrowid


def _comprovante_confirmado(con, lid, paperless_id):
    cid = con.execute("insert into comprovante(paperless_id, tipo, valor_centavos, data) values (?,?,?,?)", (paperless_id, "comprovante_pix", 1, "2026-10-01")).lastrowid
    con.execute("insert into comprovante_vinculo(comprovante_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'x','confirmado','2026-10-01')", (cid, lid))


def test_rascunho_lista_itens_com_total_e_assunto(con):
    a, b = _l(con, 1, "2026-10-01", -10000), _l(con, 2, "2026-10-05", -25050, desc="TAXI Y")
    c = montar(con, "ness", None, hoje=dt.date(2026, 10, 9))
    assert c.para == "financeiro@ness.com.br" and [i.lancamento_id for i in c.itens] == [a, b]
    assert "Ness" in c.assunto and "10/2026" in c.assunto
    assert "01/10" in c.corpo and "HOTEL X" in c.corpo and "R$ 350,50" in c.corpo  # total


def test_rascunho_lista_itens_sem_comprovante_em_aviso(con):
    a, b = _l(con, 1, "2026-10-01", -10000), _l(con, 2, "2026-10-05", -5000)
    _comprovante_confirmado(con, a, 77)
    c = montar(con, "ness", None, hoje=dt.date(2026, 10, 9))
    assert c.aviso_sem_comprovante == [b] and c.anexos == [77]


def test_montar_pode_escolher_um_subconjunto(con):
    a, _ = _l(con, 1, "2026-10-01", -10000), _l(con, 2, "2026-10-05", -5000)
    assert [i.lancamento_id for i in montar(con, "ness", [a], hoje=dt.date(2026, 10, 9)).itens] == [a]


def test_rascunho_fica_guardado_e_remontar_nao_duplica_itens(con):
    _l(con, 1, "2026-10-01", -10000)
    c = montar(con, "ness", None, hoje=dt.date(2026, 10, 9))
    assert con.execute("select count(*) from cobranca_item where cobranca_id=?", (c.id,)).fetchone()[0] == 1
    assert montar(con, "ness", None, hoje=dt.date(2026, 10, 9)).id == c.id  # mesmo rascunho aberto


def test_enviar_responde_403_nao_permitido(con):
    _l(con, 1, "2026-10-01", -10000)
    c = montar(con, "ness", None, hoje=dt.date(2026, 10, 9))
    with pytest.raises(NaoPermitido, match="rascunho"):
        enviar(con, c.id)


def test_texto_de_confirmacao_repete_destinatario_valor_e_anexos(con):
    a = _l(con, 1, "2026-10-01", -10000)
    _l(con, 2, "2026-10-05", -5000)
    _comprovante_confirmado(con, a, 77)
    c = montar(con, "ness", None, hoje=dt.date(2026, 10, 9))
    assert texto_confirmacao(c) == "Enviar para financeiro@ness.com.br, 2 itens, R$ 150,00, 1 anexos"


def test_bekaa_e_empresa_sem_email_nao_geram_cobranca(con):
    _l(con, 1, "2026-10-01", -10000, empresa="bekaa")
    _l(con, 2, "2026-10-01", -10000, empresa="ionic")
    with pytest.raises(ValueError, match="lote"):
        montar(con, "bekaa", None, hoje=dt.date(2026, 10, 9))
    with pytest.raises(ValueError, match="e-mail"):
        montar(con, "ionic", None, hoje=dt.date(2026, 10, 9))
