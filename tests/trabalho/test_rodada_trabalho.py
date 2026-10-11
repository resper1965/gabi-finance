import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.fontes.graph import ErroGraph
from gabi.fontes.google import ErroGoogle
from gabi.trabalho.rodada_trabalho import rodar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)


class GraphFalso:
    def __init__(self, erro=None):
        self.erro, self.chamadas = erro, []

    def delta_mensagens(self, caixa, cursor):
        self.chamadas.append(("msgs", caixa, cursor))
        if self.erro:
            raise self.erro
        return [{"message_id": "<a@x>", "remetente": "cli@x.com", "assunto": "oi", "recebido_em": "2026-10-09T10:00:00Z", "trecho": "t"}], "delta2"

    def delta_eventos(self, caixa, cursor):
        return [{"externo_id": "e1", "inicio": "2026-10-11T10:00:00", "fim": "2026-10-11T11:00:00", "titulo": "Reunião"}], "d"

    def tarefas(self, caixa):
        return [{"externo_id": "l/t1", "titulo": "Ligar", "prazo": None, "concluida": False}]


class GoogleFalso:
    def __init__(self):
        self.chamadas = []

    def historico_gmail(self, caixa, cursor):
        self.chamadas.append(cursor)
        return [{"message_id": "<a@x>", "remetente": "cli@x.com", "assunto": "oi", "recebido_em": "2026-10-09T10:00:00Z", "trecho": "t"}], "99"

    def eventos(self, caixa, sync):
        return [], None

    def tasks(self, caixa):
        return []


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _caixa(con, endereco, provedor, estado="sim", le=1):
    return con.execute("insert into caixa_email(endereco, provedor, estado, le) values (?,?,?,?)", (endereco, provedor, estado, le)).lastrowid


def test_le_email_agenda_e_tarefas_so_das_caixas_liberadas(con):
    ok = _caixa(con, "a@ionic.health", "graph")
    _caixa(con, "b@ness.com.br", "graph", estado="a_decidir")
    _caixa(con, "c@x.com", "graph", le=0)
    g = GraphFalso()
    r = rodar(con, lambda c: g, AGORA)
    assert r.caixas == 1 and r.mensagens == 1 and r.eventos == 1 and r.tarefas == 1
    assert {c[1] for c in g.chamadas} == {"a@ionic.health"}
    assert con.execute("select caixa_id from item_email").fetchone()[0] == ok


def test_rodar_duas_vezes_nao_duplica_mensagem_nem_evento(con):
    _caixa(con, "a@ionic.health", "graph")
    g = GraphFalso()
    rodar(con, lambda c: g, AGORA)
    r = rodar(con, lambda c: g, AGORA)
    assert r.mensagens == 0
    assert con.execute("select count(*) from item_email").fetchone()[0] == 1
    assert con.execute("select count(*) from evento").fetchone()[0] == 1
    assert g.chamadas[-1][2] == "delta2"  # o cursor avançou


def test_mesmo_message_id_em_duas_caixas_entra_uma_vez(con):
    _caixa(con, "a@ness.com.br", "graph")
    _caixa(con, "a@ness.com", "google")
    rodar(con, lambda c: GraphFalso() if c["provedor"] == "graph" else GoogleFalso(), AGORA)
    assert con.execute("select count(*) from item_email").fetchone()[0] == 1


def test_credencial_recusada_vira_aviso_reconectar_e_as_outras_caixas_seguem(con):
    _caixa(con, "a@ionic.health", "graph")
    _caixa(con, "b@bekaa.eu", "google")
    r = rodar(con, lambda c: GraphFalso(ErroGraph("GET /x -> 401: expired")) if c["provedor"] == "graph" else GoogleFalso(), AGORA)
    assert r.falhas == 1 and r.mensagens == 1
    av = con.execute("select tipo, payload from aviso").fetchall()
    assert [a["tipo"] for a in av] == ["caixa_reconectar"]
    assert json.loads(av[0]["payload"])["endereco"] == "a@ionic.health"


def test_sem_credencial_configurada_tambem_pede_reconectar(con):
    _caixa(con, "a@ionic.health", "graph")
    r = rodar(con, lambda c: None, AGORA)
    assert r.falhas == 1
    assert con.execute("select tipo from aviso").fetchone()[0] == "caixa_reconectar"


def test_erro_que_nao_e_de_credencial_nao_pede_reconectar(con):
    _caixa(con, "a@ionic.health", "graph")
    r = rodar(con, lambda c: GraphFalso(ErroGraph("GET /x -> 503")), AGORA)
    assert r.falhas == 1
    assert con.execute("select count(*) from aviso").fetchone()[0] == 0


def test_voltar_a_funcionar_fecha_o_aviso_de_reconectar(con):
    cid = _caixa(con, "a@ionic.health", "graph")
    rodar(con, lambda c: GraphFalso(ErroGraph("GET /x -> 401")), AGORA)
    rodar(con, lambda c: GraphFalso(), AGORA + dt.timedelta(hours=1))
    assert con.execute("select count(*) from aviso where entregue_em is null").fetchone()[0] == 0


def test_a_rodada_fica_registrada(con):
    _caixa(con, "a@ionic.health", "graph")
    rodar(con, lambda c: GraphFalso(), AGORA)
    r = con.execute("select fonte, status, novos from rodada").fetchone()
    assert (r["fonte"], r["status"], r["novos"]) == ("trabalho", "ok", 1)


def test_conclui_na_origem_a_tarefa_pedida_pelo_painel_e_so_entao_marca(con):
    _caixa(con, "a@ionic.health", "graph")
    g = GraphFalso()
    g.concluidas = []
    g.concluir_tarefa = lambda caixa, ext: g.concluidas.append((caixa, ext))
    rodar(con, lambda c: g, AGORA)
    con.execute("update tarefa set pedido_concluir_em='2026-10-10T11:00:00+00:00' where externo_id='l/t1'")
    rodar(con, lambda c: g, AGORA)
    assert g.concluidas == [("a@ionic.health", "l/t1")]
    assert con.execute("select estado from tarefa where externo_id='l/t1'").fetchone()[0] == "concluida"


class LinearFalso:
    def __init__(self, entregas=None, erro=None):
        self.entregas, self.erro = entregas or [], erro

    def entregas_abertas(self):
        if self.erro:
            raise self.erro
        return self.entregas


E1 = {"externo_id": "a1", "identificador": "ION-1", "titulo": "Laudo", "projeto": "nCommand", "responsavel": "R", "prazo": "2026-10-20", "estado": "Todo", "atualizado_em": None}


def test_entregas_da_linear_entram_e_as_que_sairam_da_lista_somem(con):
    from gabi.fontes.linear import ErroLinear
    r = rodar(con, lambda c: None, AGORA, LinearFalso([E1, {**E1, "externo_id": "a2", "identificador": "ION-2"}]))
    assert r.entregas == 2 and con.execute("select count(*) from entrega").fetchone()[0] == 2
    rodar(con, lambda c: None, AGORA, LinearFalso([E1]))
    assert [x[0] for x in con.execute("select identificador from entrega")] == ["ION-1"]


def test_linear_com_chave_recusada_pede_reconectar(con):
    from gabi.fontes.linear import ErroLinear
    r = rodar(con, lambda c: None, AGORA, LinearFalso(erro=ErroLinear("POST /graphql -> 401")))
    assert r.falhas == 1
    assert json.loads(con.execute("select payload from aviso").fetchone()[0])["endereco"] == "Linear"


def test_todas_as_caixas_falhando_grava_a_rodada_como_erro(con):
    _caixa(con, "a@ionic.health", "graph")
    _caixa(con, "b@bekaa.eu", "graph")
    r = rodar(con, lambda c: GraphFalso(ErroGraph("GET /x -> 503")), AGORA)
    assert r.falhas == 2 and r.caixas == 2
    row = con.execute("select status, erro from rodada").fetchone()
    assert row["status"] == "erro" and "2" in row["erro"]


def test_falha_parcial_continua_ok(con):
    _caixa(con, "a@ionic.health", "graph")
    _caixa(con, "b@bekaa.eu", "google")
    rodar(con, lambda c: GraphFalso(ErroGraph("GET /x -> 503")) if c["provedor"] == "graph" else GoogleFalso(), AGORA)
    assert con.execute("select status from rodada").fetchone()[0] == "ok"
