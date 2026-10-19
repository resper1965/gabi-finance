import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.fontes.graph_ness import ErroGraphNess
from gabi.teams.coletar import coletar

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 20, 15, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@ness.com.br", estado="sim"):
    con.execute("insert into teams_fonte(conta, estado) values (?,?)", (conta, estado))


def _msg(i, quando, eu=False, mencao=False, nome="Ana"):
    return {"id": i, "quando": quando, "de_nome": nome, "de_eu": eu, "mencoes_eu": mencao}


class Falsa:
    def __init__(self, chats, msgs=None, erros=None):
        self.chats, self.msgs, self.erros, self.chamadas = chats, msgs or {}, erros or {}, []

    def teams_chats(self, conta):
        e = self.erros.get((conta, None))
        if e:
            raise e
        return self.chats.get(conta, [])

    def teams_mensagens(self, conta, chat_id, desde):
        self.chamadas.append((conta, chat_id, desde))
        e = self.erros.get((conta, chat_id))
        if e:
            raise e
        return self.msgs.get((conta, chat_id), [])


def _chat(i="c1", tipo="um_a_um", ultima="2026-10-20T14:00:00+00:00"):
    return {"chat_id": i, "tipo": tipo, "ultima_em": ultima}


def _conv(con, i="c1"):
    return con.execute("select * from teams_conversa where chat_id=?", (i,)).fetchone()


def test_um_a_um_vira_pendente(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat()]}, {("a@ness.com.br", "c1"): [_msg("1", "2026-10-20T13:00:00+00:00")]})
    r = coletar(con, p, AGORA)
    assert r == {"a@ness.com.br": {"chats": 1, "novas": 1}}
    c = _conv(con)
    assert c["ultima_para_mim_em"] == "2026-10-20T13:00:00+00:00" and c["de_nome"] == "Ana" and c["tipo"] == "um_a_um"


def test_grupo_sem_mencao_nao_vira_pendente(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat(tipo="grupo")]}, {("a@ness.com.br", "c1"): [_msg("1", "2026-10-20T13:00:00+00:00")]})
    coletar(con, p, AGORA)
    c = _conv(con)
    assert c["ultima_para_mim_em"] is None and c["de_nome"] is None and c["cursor"] == "2026-10-20T14:00:00+00:00"


def test_grupo_com_mencao_vira_pendente(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat(tipo="grupo")]}, {("a@ness.com.br", "c1"): [_msg("1", "2026-10-20T13:00:00+00:00", mencao=True)]})
    coletar(con, p, AGORA)
    assert _conv(con)["ultima_para_mim_em"] == "2026-10-20T13:00:00+00:00"


def test_minha_resposta_registra_resposta(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat()]}, {("a@ness.com.br", "c1"): [
        _msg("1", "2026-10-20T13:00:00+00:00"), _msg("2", "2026-10-20T13:30:00+00:00", eu=True)]})
    coletar(con, p, AGORA)
    c = _conv(con)
    assert c["minha_ultima_resposta_em"] == "2026-10-20T13:30:00+00:00" and c["ultima_para_mim_em"] == "2026-10-20T13:00:00+00:00"
    assert c["cursor"] == "2026-10-20T14:00:00+00:00"  # a última atividade conhecida do chat (prévia) vale mais que a última mensagem


def test_primeira_coleta_ignora_historico_antigo(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat()]})
    coletar(con, p, AGORA)
    assert p.chamadas == [("a@ness.com.br", "c1", (AGORA - dt.timedelta(hours=24)).isoformat())]
    con.execute("insert into parametro(chave, valor) values ('teams.janela_inicial_horas', ?)", (json.dumps(6),))
    p2 = Falsa({"a@ness.com.br": [_chat("c2")]})
    coletar(con, p2, AGORA)
    assert p2.chamadas[0][2] == (AGORA - dt.timedelta(hours=6)).isoformat()


def test_cursor_evita_reler(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat()]}, {("a@ness.com.br", "c1"): [_msg("1", "2026-10-20T13:00:00+00:00")]})
    coletar(con, p, AGORA)
    p.chats["a@ness.com.br"] = [_chat(ultima="2026-10-20T14:30:00+00:00")]
    r = coletar(con, p, AGORA)  # ultima_em (14:30) > cursor (14:00): lê de novo, com cursor - 1 s
    assert p.chamadas[1][2] == "2026-10-20T13:59:59+00:00"
    p2 = Falsa({"a@ness.com.br": [_chat(ultima="2026-10-20T14:00:00+00:00")]})
    r = coletar(con, p2, AGORA)
    assert p2.chamadas == [] and r["a@ness.com.br"] == {"chats": 0, "novas": 0}


def test_chat_com_403_e_pulado_e_conta_segue(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")]},
              {("a@ness.com.br", "c2"): [_msg("1", "2026-10-20T13:00:00+00:00")]},
              {("a@ness.com.br", "c1"): ErroGraphNess("_ErroStatus: GET /chats/c1/messages -> 403")})
    r = coletar(con, p, AGORA)
    assert r["a@ness.com.br"] == {"chats": 1, "novas": 1, "puladas": 1} and _conv(con, "c2") is not None
    assert con.execute("select coletada_em from teams_fonte").fetchone()["coletada_em"] == AGORA.isoformat()


def test_429_encerra_a_conta_sem_derrubar_a_outra(con):
    _fonte(con, "a@ness.com.br")
    _fonte(con, "b@ness.com.br")
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")], "b@ness.com.br": [_chat("c3")]},
              {("b@ness.com.br", "c3"): [_msg("1", "2026-10-20T13:00:00+00:00")]},
              {("a@ness.com.br", "c1"): ErroGraphNess("_ErroStatus: GET /chats/c1/messages -> 429")})
    r = coletar(con, p, AGORA)
    assert "erro" in r["a@ness.com.br"] and r["b@ness.com.br"] == {"chats": 1, "novas": 1}
    assert [c for c in p.chamadas if c[1] == "c2"] == []
    f = {x["conta"]: x for x in con.execute("select * from teams_fonte")}
    assert f["a@ness.com.br"]["ultimo_erro"] and f["a@ness.com.br"]["coletada_em"] is None
    assert f["b@ness.com.br"]["ultimo_erro"] is None and f["b@ness.com.br"]["coletada_em"] == AGORA.isoformat()


def test_erro_inesperado_na_listagem_so_derruba_a_conta(con):
    _fonte(con, "a@ness.com.br")
    _fonte(con, "b@ness.com.br")
    p = Falsa({"b@ness.com.br": []}, erros={("a@ness.com.br", None): ErroGraphNess("serviço de fontes indisponível")})
    r = coletar(con, p, AGORA)
    assert r["a@ness.com.br"] == {"erro": "serviço de fontes indisponível"} and r["b@ness.com.br"] == {"chats": 0, "novas": 0}


def test_conta_nao_liberada_nao_e_lida(con):
    _fonte(con, "a@ness.com.br", "a_decidir")
    _fonte(con, "b@ness.com.br", "nao")
    p = Falsa({})
    assert coletar(con, p, AGORA) == {} and p.chamadas == []


def test_chat_com_500_ou_400_e_pulado_e_os_outros_seguem(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2"), _chat("c3")]},
              {("a@ness.com.br", "c3"): [_msg("1", "2026-10-20T13:00:00+00:00")]},
              {("a@ness.com.br", "c1"): ErroGraphNess("_ErroStatus: GET /chats/c1/messages -> 500"),
               ("a@ness.com.br", "c2"): ErroGraphNess("_ErroStatus: GET /chats/c2/messages -> 400")})
    r = coletar(con, p, AGORA)
    assert r["a@ness.com.br"] == {"chats": 1, "novas": 1, "puladas": 2}
    f = con.execute("select ultimo_erro, coletada_em from teams_fonte").fetchone()
    assert f["coletada_em"] == AGORA.isoformat() and "2" in f["ultimo_erro"]


def test_erro_sem_status_encerra_a_conta(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")]}, erros={("a@ness.com.br", "c1"): ErroGraphNess("serviço de fontes indisponível")})
    r = coletar(con, p, AGORA)
    assert r["a@ness.com.br"] == {"erro": "serviço de fontes indisponível"} and [c for c in p.chamadas if c[1] == "c2"] == []


def test_chat_sem_mensagem_na_janela_ganha_cursor_e_nao_e_relido(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat(ultima="2026-09-01T10:00:00+00:00")]})
    coletar(con, p, AGORA)
    assert len(p.chamadas) == 1 and _conv(con)["cursor"] == "2026-09-01T10:00:00+00:00"
    coletar(con, p, AGORA)
    assert len(p.chamadas) == 1  # pulado na rodada seguinte


def test_chat_so_com_evento_de_sistema_nao_e_relido(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat(ultima="2026-10-20T14:00:00+00:00")]}, {("a@ness.com.br", "c1"): []})  # mensagens filtradas: lista vazia
    coletar(con, p, AGORA)
    coletar(con, p, AGORA)
    assert len(p.chamadas) == 1


def test_sem_ultima_em_cursor_vira_o_desde_lido(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat(ultima=None)]})
    coletar(con, p, AGORA)
    assert _conv(con)["cursor"] == (AGORA - dt.timedelta(hours=24)).isoformat()


def test_todos_os_chats_pulados_e_falha_da_conta(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")]}, erros={
        ("a@ness.com.br", "c1"): ErroGraphNess("_ErroStatus: GET /chats/c1/messages -> 403"),
        ("a@ness.com.br", "c2"): ErroGraphNess("GET /chats/c2/messages -> 404")})
    r = coletar(con, p, AGORA)
    assert "erro" in r["a@ness.com.br"]
    f = con.execute("select ultimo_erro, coletada_em from teams_fonte").fetchone()
    assert f["ultimo_erro"] and f["coletada_em"] is None


def test_troca_de_token_403_nao_e_chat_pulado(con):
    _fonte(con)
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")]}, {("a@ness.com.br", "c2"): [_msg("1", "2026-10-20T13:00:00+00:00")]},
              {("a@ness.com.br", "c1"): ErroGraphNess("troca de token -> 403")})
    r = coletar(con, p, AGORA)
    assert r["a@ness.com.br"] == {"erro": "troca de token -> 403"} and [c for c in p.chamadas if c[1] == "c2"] == []


SENTINELAS = ("SENT_CORPO", "SENT_ASSUNTO", "SENT_ANEXO", "SENT_TEXTO", "SENT_ERRO")


def _todo_texto(con):
    saida = []
    for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
        for r in con.execute(f"select * from {t}"):
            saida += [str(v) for v in tuple(r) if v is not None]
    return "\n".join(saida)


def test_nenhum_texto_em_banco_nem_saida(tmp_path, capsys):
    from gabi.teams.__main__ import main
    banco = tmp_path / "t.db"
    c = conectar(banco)
    migrar(c, MIGR)
    c.execute("insert into teams_fonte(conta, estado) values ('a@ness.com.br','sim'), ('b@ness.com.br','sim')")
    c.close()
    sujo = {**_msg("1", "2026-10-20T13:00:00+00:00", nome="Ana"), "corpo": "SENT_CORPO", "assunto": "SENT_ASSUNTO", "anexos": ["SENT_ANEXO"], "texto": "SENT_TEXTO"}
    p = Falsa({"a@ness.com.br": [_chat("c1"), _chat("c2")], "b@ness.com.br": [_chat("c3")]},
              {("a@ness.com.br", "c1"): [sujo]},
              {("a@ness.com.br", "c2"): ErroGraphNess("_ErroStatus: GET /chats/c2/messages -> 500 SENT_ERRO"),
               ("b@ness.com.br", "c3"): ErroGraphNess("_ErroStatus: GET /chats/c3/messages -> 429 SENT_ERRO")})
    p.configurada = lambda: True
    assert main(banco, ponte=p) == 0
    cap = capsys.readouterr()
    c = conectar(banco)
    tudo = _todo_texto(c) + cap.out + cap.err
    assert "Ana" in _todo_texto(c) and "Ana" not in cap.out + cap.err
    assert not [s for s in SENTINELAS if s in tudo]
    assert c.execute("select count(*) from rodada where fonte='teams'").fetchone()[0] == 1
