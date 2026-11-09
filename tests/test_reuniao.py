"""preparar_reuniao (ADR-037): junta o que o brain sabe sobre o assunto do título de um evento. Só leitura. AGORA = 09/11/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import reuniao
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into agenda_fonte(id, conta, provedor, estado) values (1,'ness','graph','sim')")
    return c


def _evento(con, id_, titulo, inicio_utc, dia="2026-11-09", privado=0):
    con.execute("insert into agenda_evento(id, fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo, privado) values (?,?,?,?,?,?,?,?,?)",
                (id_, 1, f"x{id_}", inicio_utc, inicio_utc, dia, dia, titulo, privado))


def test_sem_evento_no_periodo(con):
    assert reuniao.preparar_reuniao(con, AGORA)["evento"] is None


def test_vazio_pega_o_proximo_que_comeca(con):
    _evento(con, 1, "Café com Marina", "2026-11-09T12:00:00+00:00")   # 09:00 local, já passou
    _evento(con, 2, "Alinhamento FGV proposta", "2026-11-09T19:00:00+00:00")
    r = reuniao.preparar_reuniao(con, AGORA)
    assert r["evento"]["id"] == 2 and "fgv" in r["termos_usados"] and "proposta" in r["termos_usados"]
    assert "alinhamento" not in r["termos_usados"]  # palavra genérica fica de fora


def test_por_trecho_do_titulo_e_por_id(con):
    _evento(con, 1, "Reunião Bekaa", "2026-11-09T19:00:00+00:00")
    _evento(con, 2, "Call ORM Reis", "2026-11-10T14:00:00+00:00", dia="2026-11-10")
    assert reuniao.preparar_reuniao(con, AGORA, "orm")["evento"]["id"] == 2
    assert reuniao.preparar_reuniao(con, AGORA, "1")["evento"]["id"] == 1


def test_junta_atividades_projetos_emails_e_a_receber(con, monkeypatch):
    _evento(con, 1, "Reunião Bekaa contrato", "2026-11-09T19:00:00+00:00")
    con.execute("insert into atividade(texto, status, origem, criada_em) values ('mandar contrato Bekaa','aberta','hermes','2026-11-01T00:00:00+00:00')")
    con.execute("insert into atividade(texto, status, origem, criada_em) values ('outra coisa','aberta','hermes','2026-11-01T00:00:00+00:00')")
    con.execute("insert into projeto(nome, objetivo, status, origem, criado_em) values ('Contrato Bekaa 2027','x','ativo','hermes','2026-11-01T00:00:00+00:00')")
    con.execute("insert into email_fonte(id, conta, provedor, estado) values (1,'a@x','google','sim')")
    con.execute("insert into email_msg(fonte_id, externo_id, remetente, assunto, recebida_em, estado) values (1,'m1','Ana <ana@bekaa.com>','Minuta do contrato','2026-11-05T10:00:00+00:00','classificada')")
    con.execute("insert into email_msg(fonte_id, externo_id, remetente, assunto, recebida_em, estado) values (1,'m2','x@y','Bekaa lixo','2026-11-05T10:00:00+00:00','na_lixeira')")
    con.execute("insert into email_msg(fonte_id, externo_id, remetente, assunto, recebida_em, estado) values (1,'m3','x@y','Bekaa antigo','2026-09-01T10:00:00+00:00','classificada')")
    monkeypatch.setattr(reuniao, "a_receber_do_mes", lambda con, hoje: {
        "recorrentes": [{"pagador": "Bekaa Ltda", "situacao": "atrasado", "esperado_centavos": 900_00, "dias_atraso": 4},
                        {"pagador": "FGV", "situacao": "a_receber", "esperado_centavos": 1, "dias_atraso": 0}], "notas": []})
    con.execute("insert into contato_google_email(conta, email, telefone, nome) values ('a@x','ana@bekaa.com','5511999990000','Ana Bekaa')")
    r = reuniao.preparar_reuniao(con, AGORA)
    assert [c["nome"] for c in r["contatos"]] == ["Ana Bekaa"]
    assert [a["texto"] for a in r["atividades"]] == ["mandar contrato Bekaa"]
    assert [p["nome"] for p in r["projetos"]] == ["Contrato Bekaa 2027"]
    assert [e["assunto"] for e in r["emails"]] == ["Minuta do contrato"]
    assert [i["pagador"] for i in r["a_receber"]] == ["Bekaa Ltda"]


def test_titulo_privado_nao_vira_busca(con):
    _evento(con, 1, "Consulta médica Fulano", "2026-11-09T19:00:00+00:00", privado=1)
    con.execute("insert into parametro(chave, valor) values ('agenda.privados', '\"ocultar\"')")
    r = reuniao.preparar_reuniao(con, AGORA)
    assert r["termos_usados"] == [] and r["evento"]["titulo"] == "Compromisso privado"
