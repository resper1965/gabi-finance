import datetime as dt
import json

from gabi.avisos import RESOLVIDO, VALE, gerar_avisos, revalidar, triar
from gabi.rotas.avisos import descrever
from tests.test_avisos import AGORA, _tipos, con  # noqa: F401

UTC = dt.timezone.utc
ANTIGA = "2026-10-15T20:00:00+00:00"   # quinta 17:00 BRT: 3 horas úteis até AGORA (sexta 09:00 BRT)
RECENTE = "2026-10-16T11:00:00+00:00"  # sexta 08:00 BRT: 1 hora útil


def _conv(con, para_mim=ANTIGA, resposta=None, tipo="um_a_um", conta="a@ness.com.br", chat="c1", estado="sim", nome="Maria", aviso=None):
    con.execute("insert or ignore into teams_fonte(conta, estado) values (?,?)", (conta, estado))
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome, ultima_para_mim_em, minha_ultima_resposta_em, ultimo_aviso_em) values (?,?,?,?,?,?,?)",
                (conta, chat, tipo, nome, para_mim, resposta, aviso))


def test_teams_um_a_um_depois_de_2h_uteis_gera_aviso(con):
    _conv(con)
    assert len(gerar_avisos(con, AGORA)) == 1 and _tipos(con) == ["teams_sem_resposta"]
    assert con.execute("select ultimo_aviso_em from teams_conversa").fetchone()[0] == AGORA.isoformat()


def test_teams_antes_de_2h_uteis_nao_gera(con):
    _conv(con, para_mim=RECENTE)
    assert gerar_avisos(con, AGORA) == []


def test_teams_grupo_sem_mencao_nao_gera(con):
    _conv(con, para_mim=None, tipo="grupo")
    assert gerar_avisos(con, AGORA) == []


def test_teams_conta_nao_sim_nao_gera(con):
    _conv(con, estado="a_decidir")
    assert gerar_avisos(con, AGORA) == []


def test_teams_respondi_antes_do_envio_e_resolvido(con):
    _conv(con)
    gerar_avisos(con, AGORA)
    r = con.execute("select id, tipo, payload from aviso").fetchone()
    con.execute("update teams_conversa set minha_ultima_resposta_em=?", (RECENTE,))
    estado, _ = triar(con, r["id"], r["tipo"], json.loads(r["payload"]), AGORA)
    assert estado == RESOLVIDO
    a = con.execute("select telegram_em, entregue_em from aviso").fetchone()
    assert a[0] is not None and a[0] == a[1]


def test_teams_vale_e_linha_sumida_resolve(con):
    _conv(con)
    gerar_avisos(con, AGORA)
    p = json.loads(con.execute("select payload from aviso").fetchone()[0])
    assert revalidar(con, "teams_sem_resposta", p)[0] == VALE
    con.execute("update teams_fonte set estado='nao'")
    assert revalidar(con, "teams_sem_resposta", p)[0] == RESOLVIDO
    con.execute("delete from teams_conversa")
    assert revalidar(con, "teams_sem_resposta", p)[0] == RESOLVIDO


def test_teams_nao_repete_para_a_mesma_mensagem(con):
    _conv(con)
    gerar_avisos(con, AGORA)
    assert gerar_avisos(con, AGORA + dt.timedelta(days=1)) == []
    assert len(con.execute("select 1 from aviso").fetchall()) == 1


def test_teams_mensagem_nova_depois_do_aviso_gera_outro_no_dia_seguinte(con):
    _conv(con)
    gerar_avisos(con, AGORA)
    dia2 = AGORA + dt.timedelta(days=3)  # segunda 09:00 BRT
    con.execute("update teams_conversa set ultima_para_mim_em=?", ("2026-10-16T20:00:00+00:00",))  # sexta 17:00 BRT
    assert len(gerar_avisos(con, dia2)) == 1
    assert len(con.execute("select 1 from aviso").fetchall()) == 2
    # mensagem nova no MESMO dia, já avisada: não cria segundo aviso
    con.execute("update teams_conversa set ultima_para_mim_em=?", ("2026-10-19T12:00:00+00:00",))  # segunda 09:00 BRT (antes do aviso, depois reavisado)
    assert gerar_avisos(con, dia2 + dt.timedelta(hours=3)) == []
    assert len(con.execute("select 1 from aviso").fetchall()) == 2


def test_teams_madrugada_e_fim_de_semana_nao_criam(con):
    _conv(con)
    assert gerar_avisos(con, dt.datetime(2026, 10, 16, 3, 5, tzinfo=UTC)) == []  # sexta 00:05 BRT
    assert gerar_avisos(con, dt.datetime(2026, 10, 17, 13, 0, tzinfo=UTC)) == []  # sábado 10:00 BRT
    assert con.execute("select count(*) from aviso").fetchone()[0] == 0
    assert len(gerar_avisos(con, AGORA)) == 1  # dia útil 09:00 BRT


def test_teams_payload_sem_texto(con):
    _conv(con)
    gerar_avisos(con, AGORA)
    p = json.loads(con.execute("select payload from aviso").fetchone()[0])
    assert set(p) <= {"chave", "conta", "chat_id", "tipo_chat", "de_nome", "desde"}
    assert p["chave"] == "a@ness.com.br|c1" and p["tipo_chat"] == "um_a_um" and p["desde"] == ANTIGA


def test_descrever_teams_um_a_um_e_mencao():
    p = {"conta": "a@ness.com.br", "de_nome": "Maria", "tipo_chat": "um_a_um", "desde": ANTIGA}
    assert descrever("teams_sem_resposta", p) == ("Teams: Maria te chamou", "sem resposta desde 15/10 17:00 (a@ness.com.br)")
    assert descrever("teams_sem_resposta", {**p, "tipo_chat": "grupo"})[0] == "Teams: Maria te mencionou"
    t, x = descrever("teams_sem_resposta", {"conta": "a@ness.com.br", "tipo_chat": "um_a_um", "desde": "lixo"})
    assert t == "Teams: Alguém te chamou" and x == "sem resposta (a@ness.com.br)"
