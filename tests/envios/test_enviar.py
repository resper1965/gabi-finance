import fcntl
import json

import pytest

from tests.envios.test_ciclo import _estado, _ligar
from tests.envios.test_propostas import AGORA, NESS, _agenda, _codigo, _convite, _evento, _teams, con  # noqa: F401

from gabi.envios import propostas as p
from gabi.envios.enviar import enviar

GMAIL = "resper@gmail.com"


class Falso:
    """Provedor falso: registra as chamadas e devolve `resp` ou levanta `erro`."""

    def __init__(self, erro: Exception | None = None, resp: dict | None = None):
        self.chamadas: list[tuple] = []
        self.erro, self.resp = erro, resp or {"externo_id": "ext-1"}

    def _fazer(self, *a):
        self.chamadas.append(a)
        if self.erro:
            raise self.erro
        return self.resp

    def evento_criar(self, conta, chave, evento):
        return self._fazer("evento_criar", conta, chave, evento)

    def convite_responder(self, conta, chave, evento_id, resposta, serie_id):
        return self._fazer("convite_responder", conta, chave, evento_id, resposta, serie_id)

    def teams_chat_enviar(self, conta, chat_id, texto):
        return self._fazer("teams_chat_enviar", conta, chat_id, texto)

    def teams_canal_enviar(self, conta, equipe_id, canal_id, texto):
        return self._fazer("teams_canal_enviar", conta, equipe_id, canal_id, texto)


def _hash(con, id):
    return _estado(con, id)["hash"]


def _chat(con, texto="oi <b>&"):
    _teams(con)
    con.execute("insert into teams_conversa(conta, chat_id, tipo, de_nome) values (?, 'c1','um_a_um','Ana Souza')", (NESS,))
    return p.criar_teams_chat(con, AGORA, conta=NESS, chat_com="Ana Souza", texto=texto)


def _canal(con):
    _teams(con)
    return p.criar_teams_canal(con, AGORA, conta=NESS, equipe_id="e1", canal_id="k1", equipe_nome="Time", canal_nome="Geral", texto="aviso")


def test_evento_google_ok(con):
    _agenda(con, conta=GMAIL, provedor="google")
    _ligar(con)
    r = _evento(con, conta=GMAIL)
    google, graph = Falso(resp={"externo_id": "g-1", "ja_existia": False}), Falso()
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, google, graph)
    assert out == {"id": r["id"], "estado": "enviada"}
    l = _estado(con, r["id"])
    assert l["estado"] == "enviada" and l["externo_id"] == "g-1" and l["enviada_em"]
    assert len(google.chamadas) == 1 and graph.chamadas == []
    _, conta, chave, evento = google.chamadas[0]
    assert conta == GMAIL and chave == l["chave"] and evento == json.loads(l["conteudo"])


def test_evento_graph_ok(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    google, graph = Falso(), Falso(resp={"externo_id": "m-1"})
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, google, graph)["estado"] == "enviada"
    assert google.chamadas == [] and graph.chamadas[0][:3] == ("evento_criar", NESS, _estado(con, r["id"])["chave"])
    assert _estado(con, r["id"])["externo_id"] == "m-1"


def test_teams_chat_ok(con):
    _ligar(con)
    r = _chat(con)
    graph = Falso()
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)["estado"] == "enviada"
    assert graph.chamadas == [("teams_chat_enviar", NESS, "c1", "oi <b>&")]


def test_teams_canal_ok(con):
    _ligar(con)
    r = _canal(con)
    graph = Falso()
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)["estado"] == "enviada"
    assert graph.chamadas == [("teams_canal_enviar", NESS, "e1", "k1", "aviso")]


def test_google_403_falhou_provedor_403(con):
    _agenda(con, conta=GMAIL, provedor="google")
    _ligar(con)
    r = _evento(con, conta=GMAIL)
    google = Falso(erro=RuntimeError("calendar.events.insert -> 403"))
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, google, None)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "provedor_403"}
    l = _estado(con, r["id"])
    assert l["estado"] == "falhou" and l["motivo"] == "provedor_403" and l["externo_id"] is None


def test_graph_503_incerto_provedor_503(con):
    _ligar(con)
    r = _chat(con)
    graph = Falso(erro=RuntimeError("POST /chats/c1/messages -> 503"))
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)
    assert out == {"id": r["id"], "estado": "incerto", "motivo": "provedor_503"}
    assert len(graph.chamadas) == 1 and _estado(con, r["id"])["motivo"] == "provedor_503"


def test_google_conta_nao_autorizada_com_conta_na_mensagem(con):
    _agenda(con, conta=GMAIL, provedor="google")
    _ligar(con)
    r = _evento(con, conta=GMAIL)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, Falso(erro=RuntimeError(f"conta não autorizada: {GMAIL}")), None)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "conta_nao_permitida"}
    assert _estado(con, r["id"])["motivo"] == "conta_nao_permitida"
    textos = [x[0] for x in con.execute("select o_que from decisao where origem='envios'")]
    assert all("conta não autorizada" not in t for t in textos)  # a mensagem do provedor não vai para decisao


def test_prefixo_do_tipo_da_ponte(con):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("ErroGraphNess: teams_sem_login")))
    assert out["estado"] == "falhou" and out["motivo"] == "teams_sem_login"


def test_token_recusado_login_google_expirado(con):
    _agenda(con, conta=GMAIL, provedor="google")
    _ligar(con)
    r = _evento(con, conta=GMAIL)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, Falso(erro=RuntimeError(f"token recusado: {GMAIL}")), None)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "login_google_expirado"}


@pytest.mark.parametrize("msg", ["chave inválida", "evento inválido", "chat inválido"])
def test_recusa_de_formato_requisicao_invalida(con, msg):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError(msg)))
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "requisicao_invalida"}


@pytest.mark.parametrize("msg", ["texto inválido", "equipe inválida", "canal inválido", "conta inválida", "link inválido",
                                 "ErroGraphNess: texto inválido", "ErroGoogleOAuth: conta inválida"])
def test_recusa_certa_antes_do_envio_falhou_requisicao_invalida(con, msg):
    """Recusas das fontes antes de qualquer requisição (nada saiu): falhou, não incerto."""
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError(msg)))
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "requisicao_invalida"}


@pytest.mark.parametrize("msg", ["troca de token -> 503", "GET /me -> 502"])
def test_5xx_antes_do_envio_continua_incerto(con, msg):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError(msg)))
    assert out["estado"] == "incerto"


def test_timeout_teams_incerto_uma_chamada(con):
    _ligar(con)
    r = _chat(con)
    graph = Falso(erro=TimeoutError("timed out"))
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)
    assert out == {"id": r["id"], "estado": "incerto", "motivo": "sem_confirmacao"}
    assert len(graph.chamadas) == 1 and _estado(con, r["id"])["estado"] == "incerto"


def test_servico_indisponivel_incerto(con):
    _ligar(con)
    r = _chat(con)
    graph = Falso(erro=RuntimeError("serviço de fontes indisponível"))
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)["motivo"] == "sem_confirmacao"


def test_login_expirado_motivo_fixo(con):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("login_teams_expirado")))
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "login_teams_expirado"}


def test_conta_nao_autorizada_vira_conta_nao_permitida(con):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("conta não autorizada")))
    assert out["estado"] == "falhou" and out["motivo"] == "conta_nao_permitida"


def test_provedor_ausente(con):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, Falso(), None)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "fonte_indisponivel"}
    assert _estado(con, r["id"])["estado"] == "falhou"


def test_desligado_nao_chama_provedor(con):
    _agenda(con)
    r = _evento(con)
    graph = Falso()
    assert _codigo(enviar, con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph).codigo == "envios_desligados"
    assert graph.chamadas == [] and _estado(con, r["id"])["estado"] == "pendente"


def test_criada_desligada_envia_depois_de_ligar(con):
    _agenda(con)
    r = _evento(con)  # criada com a escrita desligada
    _ligar(con)
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso())["estado"] == "enviada"


def test_duas_chamadas_seguidas_um_envio(con):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    graph = Falso()
    h = _hash(con, r["id"])
    assert enviar(con, r["id"], h, "ricardo", AGORA, None, graph)["estado"] == "enviada"
    assert _codigo(enviar, con, r["id"], h, "ricardo", AGORA, None, graph).codigo == "conflito"
    assert len(graph.chamadas) == 1


def test_trava_ocupada_conflito_antes_de_reservar(con, tmp_path):
    _agenda(con)
    _ligar(con)
    r = _evento(con)
    (tmp_path / "locks").mkdir(exist_ok=True)
    with open(tmp_path / "locks" / "envios.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        graph = Falso()
        assert _codigo(enviar, con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph).codigo == "conflito"
    assert graph.chamadas == [] and _estado(con, r["id"])["estado"] == "pendente"


def test_auditoria_e_stderr_sem_conteudo(con, capsys):
    _agenda(con)
    _ligar(con)
    r = _evento(con, titulo="Segredo Titulo")
    enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("POST /me/events -> 500")))
    c = _chat(con, texto="Texto Secreto")
    enviar(con, c["id"], _hash(con, c["id"]), "ricardo", AGORA, None, Falso(erro=TimeoutError("x")))
    out, err = capsys.readouterr()
    for s in ("Segredo Titulo", "Texto Secreto", "ana@x.com", "Ana Souza"):
        assert s not in out and s not in err
    auditoria = [x[0] for x in con.execute("select o_que from decisao where origem='envios' order by rowid")]
    assert len(auditoria) == 4  # reservar + concluir de cada uma, sem linha duplicada
    assert auditoria[1].endswith("incerto") and auditoria[3].endswith("incerto")
    assert all("Segredo" not in a and "Secreto" not in a and "Ana" not in a for a in auditoria)


# ---- convite_resposta ----

def _proposta_convite(con, resposta="aceitar", serie=None):
    _agenda(con)
    _ligar(con)
    return p.criar_convite_resposta(con, AGORA, conta=NESS, evento_id=_convite(con, serie=serie), resposta=resposta)


def test_convite_resposta_ok_enviada_com_externo_id(con):
    r = _proposta_convite(con, "recusar")
    google, graph = Falso(), Falso(resp={"externo_id": "AAMk-1"})
    assert enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, google, graph) == {"id": r["id"], "estado": "enviada"}
    l = _estado(con, r["id"])
    assert l["estado"] == "enviada" and l["externo_id"] == "AAMk-1" and l["enviada_em"]
    assert google.chamadas == [] and graph.chamadas == [("convite_responder", NESS, l["chave"], "AAMk-1", "recusar", None)]


def test_convite_resposta_de_serie_leva_o_serie_id(con):
    r = _proposta_convite(con, serie="AAMk-serie")
    graph = Falso()
    enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)
    assert graph.chamadas[0][-1] == "AAMk-serie" and graph.chamadas[0][3] == "AAMk-1"


@pytest.mark.parametrize("status", ["404", "409"])
def test_convite_resposta_404_409_falhou_convite_obsoleto(con, status):
    r = _proposta_convite(con)
    graph = Falso(erro=RuntimeError(f"ErroGraphNess: convite_responder -> {status}"))
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "convite_obsoleto"}
    assert len(graph.chamadas) == 1 and _estado(con, r["id"])["motivo"] == "convite_obsoleto"


def test_convite_resposta_500_incerto_sem_repetir(con):
    r = _proposta_convite(con)
    graph = Falso(erro=RuntimeError("convite_responder -> 500"))
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph)
    assert out == {"id": r["id"], "estado": "incerto", "motivo": "provedor_500"}
    assert len(graph.chamadas) == 1
    assert _codigo(enviar, con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, graph).codigo == "conflito"
    assert len(graph.chamadas) == 1


def test_convite_resposta_403_falhou_provedor_403(con):
    r = _proposta_convite(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("convite_responder -> 403")))
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "provedor_403"}


def test_404_em_outro_tipo_continua_provedor_404(con):
    _ligar(con)
    r = _chat(con)
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("POST /chats/c1/messages -> 404")))
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "provedor_404"}


def test_convite_resposta_sem_graph_fonte_indisponivel(con):
    r = _proposta_convite(con)
    google = Falso()
    out = enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, google, None)
    assert out == {"id": r["id"], "estado": "falhou", "motivo": "fonte_indisponivel"} and google.chamadas == []


def test_convite_resposta_depois_de_falhou_pode_propor_e_enviar_de_novo(con):
    r = _proposta_convite(con)
    ev = json.loads(_estado(con, r["id"])["conteudo"])["evento_id"]
    enviar(con, r["id"], _hash(con, r["id"]), "ricardo", AGORA, None, Falso(erro=RuntimeError("convite_responder -> 409")))
    r2 = p.criar_convite_resposta(con, AGORA, conta=NESS, evento_id=ev, resposta="talvez")
    assert enviar(con, r2["id"], _hash(con, r2["id"]), "ricardo", AGORA, None, Falso())["estado"] == "enviada"
