import json
from pathlib import Path

import pytest

from gabi.correio import sincronizar as sz
from gabi.db import conectar, migrar
from gabi.fontes.google_email import ResultadoEmail
from gabi.fontes.google_oauth import ErroGoogleOAuth

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-12T12:00:00+00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com", estado="sim", lixeira=0):
    return con.execute("insert into email_fonte(conta, provedor, estado, lixeira) values (?, 'google', ?, ?)", (conta, estado, lixeira)).lastrowid


def _m(ext, assunto="Reunião", de="ana@x.com", lista=False, thread=None):
    return {"externo_id": ext, "thread_id": thread or ext + "t", "remetente": de, "assunto": assunto, "recebida_em": "2026-10-12T10:00:00+00:00",
            "trecho": "texto", "lista": lista}


class Falso:
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, conta, history_id, janela_dias):
        self.chamadas.append((conta, history_id, janela_dias))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _ids(con):
    return sorted(r[0] for r in con.execute("select externo_id from email_msg"))


def test_carga_inicial_grava_mensagens_e_history_id(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([_m("a1"), _m("b2", lista=True)], "H1", False))
    r = sz.sincronizar_fonte(con, f, cli, AGORA)
    assert r == {"lidos": 2, "novos": 2, "pulados": 0, "recarga": True}
    assert _ids(con) == ["a1", "b2"]
    row = con.execute("select * from email_fonte where id=?", (f,)).fetchone()
    assert row["history_id"] == "H1" and row["sincronizada_em"] == AGORA and row["recarga_em"] == AGORA and row["ultimo_erro"] is None
    m = con.execute("select * from email_msg where externo_id='b2'").fetchone()
    assert (m["estado"], m["classe"], m["lista"], m["remetente"], m["tentativas"]) == ("nova", None, 1, "ana@x.com", 0)
    assert cli.chamadas == [("a@x.com", None, 14)]


def test_incremental_so_aplica_o_novo_e_nao_mexe_no_que_ja_foi_processado(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([_m("a1")], "H1", False), ResultadoEmail([_m("a1", assunto="outro"), _m("c3")], "H2", False))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    con.execute("update email_msg set estado='restaurada', classe='lixo' where externo_id='a1'")
    r = sz.sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert cli.chamadas[1][1] == "H1" and r == {"lidos": 2, "novos": 1, "pulados": 0, "recarga": False}
    a = con.execute("select estado, classe, assunto from email_msg where externo_id='a1'").fetchone()
    assert tuple(a) == ("restaurada", "lixo", "Reunião")  # reler nunca reabre nem reclassifica
    assert con.execute("select history_id from email_fonte").fetchone()[0] == "H2"


def test_falha_na_leitura_nao_grava_nem_troca_o_history_id(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([_m("a1")], "H1", False), ErroGoogleOAuth("messages.get -> 500"))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    with pytest.raises(ErroGoogleOAuth):
        sz.sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert _ids(con) == ["a1"] and tuple(con.execute("select history_id, sincronizada_em from email_fonte").fetchone()) == ("H1", AGORA)


def test_history_expirado_recarrega_e_renova_a_data_da_recarga(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([_m("a1")], "H1", False), ResultadoEmail([_m("a1"), _m("z9")], "H9", True))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    r = sz.sincronizar_fonte(con, f, cli, "2026-10-12T12:15:00+00:00")
    assert r["recarga"] is True and _ids(con) == ["a1", "z9"]
    assert tuple(con.execute("select history_id, recarga_em from email_fonte").fetchone()) == ("H9", "2026-10-12T12:15:00+00:00")


def test_recarga_semanal(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([], "H1", False), ResultadoEmail([], "H2", False), ResultadoEmail([], "H3", False))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    sz.sincronizar_fonte(con, f, cli, "2026-10-18T12:00:00+00:00")  # 6 dias: incremental
    assert cli.chamadas[1][1] == "H1"
    r = sz.sincronizar_fonte(con, f, cli, "2026-10-19T12:00:01+00:00")  # > 7 dias: refaz a janela
    assert cli.chamadas[2][1] is None and r["recarga"] is True


def test_mensagem_malformada_e_pulada_e_contada(con):
    f = _fonte(con)
    ruim = {"externo_id": "", "recebida_em": "2026-10-12T10:00:00+00:00"}
    sem_data = {"externo_id": "x9", "thread_id": "t", "remetente": "a@x.com", "assunto": "s", "trecho": "", "lista": False}
    r = sz.sincronizar_fonte(con, f, Falso(ResultadoEmail([ruim, sem_data, "texto", _m("ok1")], "H", False)), AGORA)
    assert r["pulados"] == 3 and r["novos"] == 1 and _ids(con) == ["ok1"]


def test_janela_vem_do_parametro(con):
    f = _fonte(con)
    con.execute("insert into parametro(chave, valor) values ('email.janela_dias', '30')")
    cli = Falso(ResultadoEmail([], "H", False))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    assert cli.chamadas[0][2] == 30


def test_uma_fonte_falha_e_a_outra_sincroniza(con):
    f1, f2 = _fonte(con, "ruim@x.com"), _fonte(con, "boa@x.com")

    def listar(conta, h, j):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("messages.list -> 500")
        return ResultadoEmail([_m("n1")], "H", False)
    r = sz.sincronizar(con, listar, AGORA)
    assert r[f1] == {"erro": "messages.list -> 500"} and r[f2]["novos"] == 1
    assert con.execute("select ultimo_erro from email_fonte where id=?", (f1,)).fetchone()[0] == "messages.list -> 500"


def test_excecao_inesperada_numa_fonte_nao_derruba_as_outras_nem_vaza_texto(con):
    f1, f2 = _fonte(con, "a@x.com"), _fonte(con, "b@x.com")

    def listar(conta, h, j):
        if conta == "a@x.com":
            raise ValueError("SEGREDO-ASSUNTO")
        return ResultadoEmail([_m("n1")], "H", False)
    r = sz.sincronizar(con, listar, AGORA)
    assert r[f1] == {"erro": "ValueError"} and r[f2]["novos"] == 1
    assert "SEGREDO" not in json.dumps(r) and "SEGREDO" not in (con.execute("select ultimo_erro from email_fonte where id=?", (f1,)).fetchone()[0] or "")


def test_fonte_a_decidir_ou_nao_nunca_e_lida(con):
    _fonte(con, estado="a_decidir"); _fonte(con, "b@x.com", estado="nao")
    cli = Falso()
    assert sz.sincronizar(con, cli, AGORA) == {} and cli.chamadas == []


def _avisos(con):
    return [json.loads(r["payload"]) for r in con.execute("select payload from aviso where tipo='email_reconectar' and entregue_em is null")]


def test_credencial_recusada_gera_um_aviso_por_dia_e_fecha_ao_voltar(con):
    _fonte(con, "a@x.com")
    erro = ErroGoogleOAuth("conta não autorizada: a@x.com")
    cli = Falso(erro, erro, ResultadoEmail([], "H", False))
    sz.sincronizar(con, cli, AGORA)
    sz.sincronizar(con, cli, "2026-10-12T12:15:00+00:00")
    assert len(_avisos(con)) == 1 and set(_avisos(con)[0]) == {"chave", "conta"} and _avisos(con)[0]["conta"] == "a@x.com"
    sz.sincronizar(con, cli, "2026-10-12T12:30:00+00:00")
    assert _avisos(con) == []


def test_erro_comum_nao_gera_aviso_de_reconectar(con):
    _fonte(con)
    sz.sincronizar(con, Falso(ErroGoogleOAuth("Google indisponível: TimeoutError")), AGORA)
    assert _avisos(con) == []


def test_idempotente(con):
    f = _fonte(con)
    cli = Falso(ResultadoEmail([_m("a1"), _m("b2")], "H1", False), ResultadoEmail([_m("a1"), _m("b2")], "H1", False))
    sz.sincronizar_fonte(con, f, cli, AGORA)
    antes = [tuple(r) for r in con.execute("select * from email_msg order by id")]
    sz.sincronizar_fonte(con, f, cli, AGORA)
    assert [tuple(r) for r in con.execute("select * from email_msg order by id")] == antes


def test_atualizar_respondidos_grava_enderecos_validos_e_a_marca_de_conferencia(con):
    f = _fonte(con)
    assert sz.respondidos_prontos(con, f) is False
    n = sz.atualizar_respondidos(con, f, ["Bia@X.com", "bia@x.com", "invalido", "c@y.com", 3], AGORA)
    assert n == 2
    assert {r[0] for r in con.execute("select endereco from email_respondido where fonte_id=?", (f,))} == {"bia@x.com", "c@y.com", ""}
    assert sz.respondidos_prontos(con, f) is True
    assert sz.atualizar_respondidos(con, f, [], "2026-10-19T12:00:00+00:00") == 0  # lista vazia também vale como "conferi"
    assert sz.respondidos_prontos(con, f) is True
