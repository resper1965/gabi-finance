import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.envios import propostas as p
from gabi.envios.propostas import ErroEnvio

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
SP = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 10, 22, 9, 0, tzinfo=SP)
NESS = "resper@ness.com.br"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _agenda(con, conta=NESS, provedor="graph"):
    con.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?) on conflict(chave) do update set valor=excluded.valor",
                (json.dumps([conta]),))
    con.execute("insert into agenda_fonte(conta, provedor, calendario_id, estado) values (?,?, 'primary','sim')", (conta, provedor))


def _evento(con, **kw):
    a = dict(conta=NESS, titulo="Reunião", inicio="2026-10-23T15:00", duracao_min=60, convidados=["Ana@X.com ", " ana@x.com"])
    a.update(kw)
    return p.criar_evento(con, AGORA, **a)


def _codigo(fn, *a, **kw):
    with pytest.raises(ErroEnvio) as e:
        fn(*a, **kw)
    return e.value


def test_criar_evento_grava_conteudo_canonico_hash_e_chave(con):
    _agenda(con)
    r = _evento(con)
    assert r["estado"] == "pendente" and r["resumo"]
    l = con.execute("select * from envio_proposta where id=?", (r["id"],)).fetchone()
    assert l["estado"] == "pendente" and l["tipo"] == "evento" and l["conta"] == NESS
    assert json.loads(l["conteudo"]) == {"conta": NESS, "provedor": "graph", "titulo": "Reunião", "inicio_utc": "2026-10-23T18:00:00Z",
                                         "fim_utc": "2026-10-23T19:00:00Z", "fuso": "America/Sao_Paulo", "convidados": ["ana@x.com"],
                                         "descricao": "", "online": True}
    assert l["hash"] == hashlib.sha256(l["conteudo"].encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-v]{26}", l["chave"])
    assert r["vence_em"] == l["vence_em"]


@pytest.mark.parametrize("ini", ["2026-10-23T18:00:00Z", "2026-10-23T15:00:00-03:00", "2026-10-23T18:00:00+00:00"])
def test_inicio_com_fuso_explicito_converte(con, ini):
    _agenda(con)
    r = _evento(con, inicio=ini)
    c = json.loads(con.execute("select conteudo from envio_proposta where id=?", (r["id"],)).fetchone()[0])
    assert c["inicio_utc"] == "2026-10-23T18:00:00Z"


def test_vence_em_e_o_menor_entre_24h_e_inicio(con):
    _agenda(con)
    assert _evento(con, inicio="2026-10-22T12:00")["vence_em"] == "2026-10-22T15:00:00Z"
    assert _evento(con, inicio="2026-10-25T12:00")["vence_em"] == "2026-10-23T12:00:00Z"


def test_inicio_no_passado_recusado(con):
    _agenda(con)
    assert _codigo(_evento, con, inicio="2026-10-22T08:00").codigo == "inicio_passado"
    assert con.execute("select count(*) from envio_proposta").fetchone()[0] == 0


def test_conta_fora_da_lista_recusada(con):
    _agenda(con)
    assert _codigo(_evento, con, conta="outra@x.com").codigo == "conta_nao_permitida"


def test_conta_na_lista_sem_agenda_fonte_recusada(con):
    con.execute("insert into parametro(chave, valor) values ('envios.contas_agenda', ?)", (json.dumps([NESS]),))
    assert _codigo(_evento, con).codigo == "conta_nao_permitida"


@pytest.mark.parametrize("kw", [dict(titulo=""), dict(titulo="x" * 201), dict(duracao_min=4), dict(duracao_min=721), dict(convidados=[]),
                                dict(convidados=[f"a{i}@x.com" for i in range(31)]), dict(descricao="x" * 2001)])
def test_limites(con, kw):
    _agenda(con)
    assert _codigo(_evento, con, **kw).codigo == "requisicao_invalida"


def _contato(con, nome="João Silva", emails=("joao@x.com",), tel="+5511999990000", conta="resper@gmail.com"):
    con.execute("insert into contato_google(conta, telefone, nome) values (?,?,?)", (conta, tel, nome))
    for e in emails:
        con.execute("insert into contato_google_email(conta, email, telefone) values (?,?,?)", (conta, e, tel))


def test_convidado_por_nome_ignora_acento_e_caixa(con):
    _contato(con)
    assert p.resolver_convidados(con, ["joao silva"]) == ["joao@x.com"]
    assert p.resolver_convidados(con, ["JOÃO  SILVA"]) == ["joao@x.com"]


def test_convidado_ambiguo_lista_candidatos(con):
    _agenda(con)
    _contato(con, emails=("joao@x.com", "j2@x.com"))
    e = _codigo(_evento, con, convidados=["joao silva"])
    assert e.codigo == "convidado_ambiguo"
    assert sorted(c["email"] for c in e.candidatos) == ["j2@x.com", "joao@x.com"]
    assert con.execute("select count(*) from envio_proposta").fetchone()[0] == 0


def test_convidado_sem_contato(con):
    e = _codigo(p.resolver_convidados, con, ["fulano"])
    assert e.codigo == "convidado_ambiguo" and e.candidatos == []


def test_convidado_invalido(con):
    assert _codigo(p.resolver_convidados, con, ["a@b"]).codigo == "convidado_invalido"


def _teams(con, estado="sim"):
    con.execute("insert into teams_fonte(conta, estado) values (?,?)", (NESS, estado))


def test_criar_teams_chat_resolve_por_de_nome(con):
    _teams(con)
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'c1','um_a_um','Ana Souza')", (NESS,))
    r = p.criar_teams_chat(con, AGORA, conta=NESS, chat_com="ana souza", texto="oi <b>&")
    l = con.execute("select * from envio_proposta where id=?", (r["id"],)).fetchone()
    assert json.loads(l["conteudo"]) == {"conta": NESS, "chat_id": "c1", "destino_nome": "Ana Souza", "tipo": "um_a_um", "texto": "oi <b>&"}
    assert l["vence_em"] == "2026-10-23T12:00:00Z" and l["tipo"] == "teams_chat" and r["resumo"] == "Teams: chat com Ana Souza"
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'c2','grupo','Ana Souza')", (NESS,))
    e = _codigo(p.criar_teams_chat, con, AGORA, conta=NESS, chat_com="Ana Souza", texto="x")
    assert e.codigo == "destino_ambiguo" and len(e.candidatos) == 2


def test_criar_teams_chat_de_grupo_guarda_tipo_e_avisa_no_resumo(con):
    _teams(con)
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'g1','grupo','Bruno Lima')", (NESS,))
    r = p.criar_teams_chat(con, AGORA, conta=NESS, chat_com="Bruno Lima", texto="oi")
    l = con.execute("select conteudo, hash from envio_proposta where id=?", (r["id"],)).fetchone()
    assert json.loads(l["conteudo"])["tipo"] == "grupo" and r["resumo"] == "Teams: chat com Bruno Lima (grupo)"
    assert l["hash"] == hashlib.sha256(l["conteudo"].encode()).hexdigest()  # o tipo está coberto pelo hash


def test_teams_conta_nao_permitida(con):
    _teams(con, "nao")
    assert _codigo(p.criar_teams_chat, con, AGORA, conta=NESS, chat_com="x", texto="x").codigo == "conta_nao_permitida"
    assert _codigo(p.criar_teams_chat, con, AGORA, conta="outra@x.com", chat_com="x", texto="x").codigo == "conta_nao_permitida"


def test_criar_teams_canal_grava_ids_e_nomes(con):
    _teams(con)
    r = p.criar_teams_canal(con, AGORA, conta=NESS, equipe_id="e1", canal_id="k1", equipe_nome="Eq", canal_nome="Geral", texto="oi")
    l = con.execute("select * from envio_proposta where id=?", (r["id"],)).fetchone()
    assert l["tipo"] == "teams_canal"
    assert json.loads(l["conteudo"]) == {"conta": NESS, "equipe_id": "e1", "canal_id": "k1", "equipe_nome": "Eq", "canal_nome": "Geral", "texto": "oi"}


@pytest.mark.parametrize("t", ["", "x" * 4001])
def test_texto_teams_limites(con, t):
    _teams(con)
    assert _codigo(p.criar_teams_canal, con, AGORA, conta=NESS, equipe_id="e", canal_id="k", equipe_nome="E", canal_nome="C", texto=t).codigo == "requisicao_invalida"
    assert _codigo(p.criar_teams_chat, con, AGORA, conta=NESS, chat_com="x", texto=t).codigo == "requisicao_invalida"


def test_escrita_ligada_so_com_ligado(con):
    assert p.escrita_ligada(con) is False
    con.execute("insert into parametro(chave, valor) values ('envios.escrita', '\"ligado\"')")
    assert p.escrita_ligada(con) is True
    con.execute("update parametro set valor='true' where chave='envios.escrita'")
    assert p.escrita_ligada(con) is False


# ---- convite_resposta ----

def _convite(con, ext="AAMk-1", ini="2026-10-22T18:00:00+00:00", fim="2026-10-22T19:00:00+00:00", titulo="Comitê", resposta="needsAction",
             dia_inteiro=0, livre=0, org="Ana Souza", serie=None, conta=NESS):
    fonte = con.execute("select id from agenda_fonte where conta=?", (conta,)).fetchone()[0]
    return con.execute(
        "insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, dia_inteiro, titulo, livre, resposta, organizador_nome, serie_id)"
        " values (?,?,?,?,?,?,?,?,?,?,?,?)", (fonte, ext, ini, fim, ini[:10], fim[:10], dia_inteiro, titulo, livre, resposta, org, serie)).lastrowid


def _responder(con, evento_id, resposta="aceitar", conta=NESS, agora=AGORA):
    return p.criar_convite_resposta(con, agora, conta=conta, evento_id=evento_id, resposta=resposta)


def test_criar_convite_resposta_grava_conteudo_e_conflito(con):
    _agenda(con)
    ev = _convite(con, serie="AAMk-serie")
    _convite(con, ext="AAMk-2", titulo="Almoço", resposta="accepted", org=None, ini="2026-10-22T18:30:00+00:00", fim="2026-10-22T20:00:00+00:00")
    r = _responder(con, ev, "talvez")
    assert set(r) == {"id", "estado", "vence_em", "resumo"} and r["estado"] == "pendente"
    assert r["vence_em"] == "2026-10-22T18:00:00Z"  # o início vem antes de agora+24h
    assert r["resumo"] == "Responder 'Comitê' qui 15h–16h: talvez"
    l = con.execute("select * from envio_proposta where id=?", (r["id"],)).fetchone()
    assert l["tipo"] == "convite_resposta" and l["conta"] == NESS and l["vence_em"] == r["vence_em"]
    assert json.loads(l["conteudo"]) == {"conta": NESS, "provedor": "graph", "evento_id": ev, "externo_id": "AAMk-1", "serie_id": "AAMk-serie",
                                         "titulo": "Comitê", "inicio_utc": "2026-10-22T18:00:00Z", "fim_utc": "2026-10-22T19:00:00Z",
                                         "organizador_nome": "Ana Souza", "resposta": "talvez", "conflita_com": ["Almoço"]}
    assert l["hash"] == hashlib.sha256(l["conteudo"].encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-v]{26}", l["chave"])


def test_convite_resposta_vence_em_24h_se_inicio_e_depois(con):
    _agenda(con)
    ev = _convite(con, ini="2026-10-26T13:30:00+00:00", fim="2026-10-26T14:00:00+00:00")
    r = _responder(con, ev, "recusar")
    assert r["vence_em"] == "2026-10-23T12:00:00Z" and r["resumo"] == "Responder 'Comitê' seg 10h30–11h: recusar"
    assert json.loads(con.execute("select conteudo from envio_proposta").fetchone()[0])["conflita_com"] == []


def test_convite_resposta_conta_nao_permitida(con):
    _agenda(con)
    ev = _convite(con)
    con.execute("update parametro set valor='[]' where chave='envios.contas_agenda'")
    assert _codigo(_responder, con, ev).codigo == "conta_nao_permitida"
    assert _codigo(_responder, con, ev, conta="outra@x.com").codigo == "conta_nao_permitida"


def test_convite_resposta_evento_de_outra_conta_ou_inexistente(con):
    _agenda(con)
    _agenda(con, conta="b@x.com")  # agora só b@x.com está na lista
    ev = _convite(con)  # evento da conta NESS
    assert _codigo(_responder, con, ev, conta="b@x.com").codigo == "requisicao_invalida"
    assert _codigo(_responder, con, 9999, conta="b@x.com").codigo == "requisicao_invalida"


@pytest.mark.parametrize("kw", [dict(resposta="sim"), dict(resposta=None), dict(evento_id="1"), dict(evento_id=True)])
def test_convite_resposta_requisicao_invalida(con, kw):
    _agenda(con)
    ev = _convite(con)
    a = dict(evento_id=ev, resposta="aceitar")
    a.update(kw)
    assert _codigo(p.criar_convite_resposta, con, AGORA, conta=NESS, **a).codigo == "requisicao_invalida"
    assert con.execute("select count(*) from envio_proposta").fetchone()[0] == 0


def test_convite_resposta_evento_passado(con):
    _agenda(con)
    ev = _convite(con, ini="2026-10-22T11:00:00+00:00", fim="2026-10-22T13:00:00+00:00")
    assert _codigo(_responder, con, ev).codigo == "inicio_passado"


@pytest.mark.parametrize("kw", [dict(resposta=None), dict(resposta="accepted"), dict(resposta="declined"), dict(dia_inteiro=1)])
def test_convite_resposta_nao_pendente(con, kw):
    """Organizador (resposta nula), já respondido ou dia inteiro."""
    _agenda(con)
    ev = _convite(con, **kw)
    assert _codigo(_responder, con, ev).codigo == "convite_nao_pendente"
    assert con.execute("select count(*) from envio_proposta").fetchone()[0] == 0


def test_convite_resposta_duplicada_enquanto_pendente_ou_enviando(con):
    _agenda(con)
    ev = _convite(con)
    r = _responder(con, ev)
    assert _codigo(_responder, con, ev, "recusar").codigo == "proposta_duplicada"
    con.execute("update envio_proposta set estado='enviando' where id=?", (r["id"],))
    assert _codigo(_responder, con, ev).codigo == "proposta_duplicada"
    outro = _convite(con, ext="AAMk-3")
    assert _responder(con, outro)["estado"] == "pendente"  # outro convite não é duplicata


def test_convite_resposta_depois_de_falhou_recusada_ou_vencida_pode_propor_de_novo(con):
    _agenda(con)
    ev = _convite(con, ini="2026-10-26T13:30:00+00:00", fim="2026-10-26T14:00:00+00:00")
    r1 = _responder(con, ev)
    con.execute("update envio_proposta set estado='falhou', motivo='convite_obsoleto' where id=?", (r1["id"],))
    r2 = _responder(con, ev, "recusar")
    p.recusar(con, r2["id"], "ricardo", AGORA)
    r3 = _responder(con, ev, "talvez")
    depois = AGORA + dt.timedelta(hours=25)  # r3 venceu (24h), mesmo sem ninguém ter listado
    r4 = _responder(con, ev, agora=depois)
    assert len({r1["id"], r2["id"], r3["id"], r4["id"]}) == 4
    assert con.execute("select estado from envio_proposta where id=?", (r3["id"],)).fetchone()[0] == "vencida"
