import threading

import pytest

from gabi.fontes.ambiente import fontes_do_ambiente
from gabi.fontes.nibo import ErroNibo
from gabi.fontes.paperless import ErroPaperless
from gabi.fontes.ponte import Ponte, Servidor


class PaperlessFalso:
    def docs(self, **f):
        return [{"id": 1, "title": "x", **f}]

    def baixar(self, id):
        if id == 999:
            raise ErroPaperless("GET /x -> 500")
        return b"%PDF\x00\xff" + bytes([id])

    def preparar_usuario(self, token_admin):
        return "segredo"



class NiboFalso:
    def __init__(self):
        self.anexos = []

    def obter_arquivo(self, file_id):
        return b"\x00\x01bin" + file_id.encode()

    def agendamentos_a_receber(self):
        return iter([{"scheduleId": "s1"}])

    def nfse(self, desde=None):
        return []

    def explode(self):
        raise RuntimeError("token=abc")


@pytest.fixture
def ponte(tmp_path):
    nibo = NiboFalso()
    srv = Servidor(tmp_path / "f.sock", {"paperless": PaperlessFalso(), "nibo": nibo})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield tmp_path / "f.sock", nibo
    srv.shutdown()
    srv.server_close()


def test_chamada_simples_e_bytes_ida_e_volta(ponte):
    sock, nibo = ponte
    p, n = Ponte(sock, "paperless"), Ponte(sock, "nibo")
    assert p.docs(query="luz") == [{"id": 1, "title": "x", "query": "luz"}]
    assert p.baixar(7) == b"%PDF\x00\xff\x07"
    assert n.obter_arquivo("f") == b"\x00\x01binf"
    assert n.nfse() == []


def test_gerador_vira_lista(ponte):
    assert Ponte(ponte[0], "nibo").agendamentos_a_receber() == [{"scheduleId": "s1"}]


def test_erro_da_fonte_volta_como_a_mesma_excecao(ponte):
    with pytest.raises(ErroPaperless, match="GET /x -> 500"):
        Ponte(ponte[0], "paperless").baixar(999)


def test_metodo_fora_da_lista_branca_nao_existe_e_nem_o_servidor_aceita(ponte):
    p = Ponte(ponte[0], "paperless")
    with pytest.raises(AttributeError):
        p.preparar_usuario("tok")
    with pytest.raises(ErroPaperless, match="metodo_proibido"):
        p._chamar("preparar_usuario", ("tok",))


def test_excecao_inesperada_nao_vaza_mensagem(ponte):
    with pytest.raises(ErroNibo) as e:
        Ponte(ponte[0], "nibo")._chamar("criar_agendamento_debito", (), {"x": 1})  # o falso não tem esse método: AttributeError no servidor
    assert "token" not in str(e.value) and "abc" not in str(e.value)


def test_fonte_nao_configurada(tmp_path):
    srv = Servidor(tmp_path / "g.sock", {"paperless": None, "nibo": PaperlessFalso()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert Ponte(tmp_path / "g.sock", "paperless").configurada() is False
        assert Ponte(tmp_path / "g.sock", "nibo").configurada() is True
        with pytest.raises(ErroPaperless, match="não está configurado"):
            Ponte(tmp_path / "g.sock", "paperless").docs()
    finally:
        srv.shutdown()
        srv.server_close()


def test_servico_fora_do_ar_vira_erro_da_fonte(tmp_path):
    with pytest.raises(ErroNibo, match="indisponível"):
        Ponte(tmp_path / "nada.sock", "nibo").agendamentos_a_receber()
    assert Ponte(tmp_path / "nada.sock", "nibo").configurada() is False


def test_ambiente_com_socket_usa_a_ponte_e_devolve_none_se_nao_configurada(tmp_path, monkeypatch):
    srv = Servidor(tmp_path / "h.sock", {"paperless": PaperlessFalso(), "nibo": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "h.sock"))
        f = fontes_do_ambiente()
        assert f["nibo"]() is None
        assert f["paperless"]().baixar(2) == b"%PDF\x00\xff\x02"
    finally:
        srv.shutdown()
        srv.server_close()


def test_socket_so_para_dono_e_grupo(ponte):
    import stat
    assert stat.S_IMODE(ponte[0].stat().st_mode) == 0o660


# ---------------- Task 7a: enviar (Paperless) e openrouter ----------------
from gabi.fontes.openrouter import ErroOpenRouter, OpenRouter  # noqa: E402
from gabi.fontes.paperless import Paperless  # noqa: E402
from gabi.fontes.ponte import PonteModelo  # noqa: E402
from gabi.fontes.servico import openrouter_do_ambiente  # noqa: E402


def _servir(tmp_path, fontes):
    srv = Servidor(tmp_path / "g.sock", fontes)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, tmp_path / "g.sock"


def test_ponte_openrouter_so_completar(tmp_path):
    http = lambda *a: (200, {"choices": [{"message": {"content": "t"}}], "usage": {"cost": 0.5}})  # noqa: E731
    srv, sock = _servir(tmp_path, {"openrouter": OpenRouter("k", "a", "b", http=http)})
    try:
        assert PonteModelo(sock).completar("p", forte=True) == ("t", 0.5)
        o = Ponte(sock, "openrouter")
        with pytest.raises(AttributeError):
            o.modelo_rapido
        with pytest.raises(ErroOpenRouter, match="metodo_proibido"):
            o._chamar("__init__", ("x",))
    finally:
        srv.shutdown()
        srv.server_close()


def test_ponte_modelo_sem_chave_vira_erro_tipado(tmp_path):
    assert openrouter_do_ambiente({}) is None  # sem chave a fonte não está configurada
    srv, sock = _servir(tmp_path, {"openrouter": None})
    try:
        assert not Ponte(sock, "openrouter").configurada()
        with pytest.raises(ErroOpenRouter, match="não está configurado"):
            PonteModelo(sock).completar("p", forte=False)
    finally:
        srv.shutdown()
        srv.server_close()


def test_ponte_modelo_resposta_malformada_vira_erro_tipado(tmp_path, monkeypatch):
    m = PonteModelo(tmp_path / "x.sock")
    for ruim in ("lixo", ["t", "nao-numero"], ["t"], None):
        monkeypatch.setattr(m._ponte, "_chamar", lambda *a, **k: ruim)
        with pytest.raises(ErroOpenRouter, match="resposta inválida"):
            m.completar("p", forte=False)


def test_tag_invalida_e_erro_paperless_e_value_error():
    from gabi.fontes.paperless import TagInvalida
    assert issubclass(TagInvalida, ErroPaperless) and issubclass(TagInvalida, ValueError)


def test_openrouter_do_ambiente_modelos_e_padroes():
    o = openrouter_do_ambiente({"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL_FAST": "x/y"})
    assert (o.modelo_rapido, o.modelo_forte) == ("x/y", "anthropic/claude-sonnet-5.5")
    assert openrouter_do_ambiente({"OPENROUTER_API_KEY": "k"}).modelo_rapido == "deepseek/deepseek-v4-flash"


# ---- agenda do Google pela ponte ----
from gabi.fontes.google_agenda import ResultadoEventos  # noqa: E402
from gabi.fontes.google_oauth import ErroGoogleOAuth  # noqa: E402
from gabi.fontes.ponte import ERROS, PERMITIDOS, PonteAgenda  # noqa: E402
from gabi.fontes.servico import google_do_ambiente  # noqa: E402

SEGREDO_AG = "refresh-SEGREDO-agenda"
JANELA_AG = {"de": "2026-10-04T00:00:00+00:00", "ate": "2027-01-09T00:00:00+00:00"}


class _FalsaAgenda:
    def listar_calendarios(self, conta):
        return [{"id": "primary", "nome": "Ricardo", "principal": True}]

    def listar_eventos(self, conta, calendario_id, sync_token, janela):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("conta não autorizada: ruim@x.com")
        if conta == "boom@x.com":
            raise RuntimeError(SEGREDO_AG)
        if conta == "malformada@x.com":
            return ["isto", "não", "é", "dict"]
        if conta == "faltando@x.com":
            return {"eventos": []}
        return {"eventos": [{"externo_id": "a"}], "cancelados": ["b"], "novo_sync_token": "S", "recarga_completa": False}

    def evento_criar(self, conta, chave, evento):
        if conta == "malformada@x.com":
            return ["não", "dict"]
        if conta == "faltando@x.com":
            return {"externo_id": chave}
        return {"externo_id": chave, "ja_existia": False}

    def segredo(self):
        return SEGREDO_AG


@pytest.fixture
def sock_agenda(tmp_path):
    srv = Servidor(tmp_path / "ag.sock", {"google_agenda": _FalsaAgenda(), "paperless": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path / "ag.sock"
    srv.shutdown(); srv.server_close()


def test_ponte_permite_so_listar_calendarios_listar_eventos_e_evento_criar(sock_agenda):
    assert PERMITIDOS["google_agenda"] == frozenset({"listar_calendarios", "listar_eventos", "evento_criar"})
    assert ERROS["google_agenda"] is ErroGoogleOAuth
    with pytest.raises(ErroGoogleOAuth) as e:
        Ponte(sock_agenda, "google_agenda")._chamar("segredo")
    assert SEGREDO_AG not in str(e.value) and "metodo_proibido" in str(e.value)


def test_ponte_agenda_cruza_resultado_tipado(sock_agenda):
    p = PonteAgenda(sock_agenda)
    assert p.listar_calendarios("a@x.com") == [{"id": "primary", "nome": "Ricardo", "principal": True}]
    r = p.listar_eventos("a@x.com", "primary", None, JANELA_AG)
    assert isinstance(r, ResultadoEventos)
    assert r.eventos == [{"externo_id": "a"}] and r.cancelados == ["b"] and r.novo_sync_token == "S" and r.recarga_completa is False


def test_erro_tipado_atravessa_a_ponte_sem_segredo(sock_agenda):
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteAgenda(sock_agenda).listar_eventos("ruim@x.com", "primary", None, JANELA_AG)
    assert str(e.value) == "conta não autorizada: ruim@x.com"
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteAgenda(sock_agenda).listar_eventos("boom@x.com", "primary", None, JANELA_AG)
    assert SEGREDO_AG not in str(e.value)


@pytest.mark.parametrize("conta", ["malformada@x.com", "faltando@x.com"])
def test_ponte_agenda_valida_a_forma_da_resposta(sock_agenda, conta):
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteAgenda(sock_agenda).listar_eventos(conta, "primary", None, JANELA_AG)
    assert "resposta inválida" in str(e.value)


def test_fonte_ausente_sem_credencial(tmp_path):
    assert google_do_ambiente({}) == {"google_contatos": None, "google_agenda": None, "google_email": None}
    ok = google_do_ambiente({"GOOGLE_CLIENT_ID": "i", "GOOGLE_CLIENT_SECRET": "s"})
    assert ok["google_agenda"] is not None and ok["google_contatos"] is not None
    srv = Servidor(tmp_path / "n.sock", {"google_agenda": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = PonteAgenda(tmp_path / "n.sock")
        assert p.configurada() is False
        with pytest.raises(ErroGoogleOAuth):
            p.listar_calendarios("a@x.com")
    finally:
        srv.shutdown(); srv.server_close()


def test_ponte_agenda_indisponivel_e_erro_tipado(tmp_path):
    with pytest.raises(ErroGoogleOAuth):
        PonteAgenda(tmp_path / "nada.sock").listar_eventos("a@x.com", "primary", None, JANELA_AG)


# ---- e-mail (Gmail) do Google pela ponte ----
from gabi.fontes.google_email import ResultadoEmail  # noqa: E402
from gabi.fontes.ponte import PonteEmail  # noqa: E402

SEGREDO_EM = "refresh-SEGREDO-email"


class _FalsaEmail:
    def listar_novos(self, conta, history_id, janela_dias):
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("conta não autorizada: ruim@x.com")
        if conta == "boom@x.com":
            raise RuntimeError(SEGREDO_EM)
        if conta == "malformada@x.com":
            return ["isto", "não", "é", "dict"]
        if conta == "faltando@x.com":
            return {"mensagens": []}
        if conta == "tipo@x.com":
            return {"mensagens": ["texto"], "novo_history_id": "1", "recarga_completa": False}
        return {"mensagens": [{"externo_id": "a1"}], "novo_history_id": "H", "recarga_completa": False}

    def lixeira(self, conta, ids):
        if conta == "malformada@x.com":
            return {"a1": "talvez"}
        return {i: "ok" for i in ids}

    def restaurar(self, conta, ids):
        return {i: "ok" for i in ids}

    def enviados_recentes(self, conta, dias):
        if conta == "malformada@x.com":
            return [1, 2]
        return ["bia@x.com"]

    def respondeu_a(self, conta, enderecos):
        if conta == "malformada@x.com":
            return {"bia@x.com": "sim"}
        if conta == "ruim@x.com":
            raise ErroGoogleOAuth("messages.list -> 500")
        return {a: a.startswith("bia") for a in enderecos}

    def segredo(self):
        return SEGREDO_EM


@pytest.fixture
def sock_email(tmp_path):
    srv = Servidor(tmp_path / "em.sock", {"google_email": _FalsaEmail(), "paperless": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path / "em.sock"
    srv.shutdown(); srv.server_close()


def test_ponte_permite_so_os_cinco_metodos_do_email(sock_email):
    assert PERMITIDOS["google_email"] == frozenset({"listar_novos", "lixeira", "restaurar", "enviados_recentes", "respondeu_a"})
    assert ERROS["google_email"] is ErroGoogleOAuth
    with pytest.raises(ErroGoogleOAuth) as e:
        Ponte(sock_email, "google_email")._chamar("segredo")
    assert SEGREDO_EM not in str(e.value) and "metodo_proibido" in str(e.value)


def test_ponte_email_cruza_resultado_tipado(sock_email):
    p = PonteEmail(sock_email)
    r = p.listar_novos("a@x.com", None, 14)
    assert isinstance(r, ResultadoEmail) and r.mensagens == [{"externo_id": "a1"}] and r.novo_history_id == "H" and r.recarga_completa is False
    assert p.lixeira("a@x.com", ["a1", "b2"]) == {"a1": "ok", "b2": "ok"}
    assert p.restaurar("a@x.com", ["a1"]) == {"a1": "ok"}
    assert p.enviados_recentes("a@x.com", 365) == ["bia@x.com"]


def test_erro_tipado_do_email_atravessa_sem_segredo(sock_email):
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteEmail(sock_email).listar_novos("ruim@x.com", None, 14)
    assert str(e.value) == "conta não autorizada: ruim@x.com"
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteEmail(sock_email).listar_novos("boom@x.com", None, 14)
    assert SEGREDO_EM not in str(e.value)


@pytest.mark.parametrize("conta", ["malformada@x.com", "faltando@x.com", "tipo@x.com"])
def test_ponte_email_valida_a_forma_da_resposta(sock_email, conta):
    with pytest.raises(ErroGoogleOAuth) as e:
        PonteEmail(sock_email).listar_novos(conta, None, 14)
    assert "resposta inválida" in str(e.value)


def test_ponte_email_valida_lixeira_e_enviados(sock_email):
    p = PonteEmail(sock_email)
    for chamada in (lambda: p.lixeira("malformada@x.com", ["a1"]), lambda: p.enviados_recentes("malformada@x.com", 365)):
        with pytest.raises(ErroGoogleOAuth) as e:
            chamada()
        assert "resposta inválida" in str(e.value)


def test_fonte_de_email_ausente_sem_credencial(tmp_path):
    assert google_do_ambiente({}) == {"google_contatos": None, "google_agenda": None, "google_email": None}
    ok = google_do_ambiente({"GOOGLE_CLIENT_ID": "i", "GOOGLE_CLIENT_SECRET": "s"})
    assert ok["google_email"] is not None
    srv = Servidor(tmp_path / "n.sock", {"google_email": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = PonteEmail(tmp_path / "n.sock")
        assert p.configurada() is False
        with pytest.raises(ErroGoogleOAuth):
            p.listar_novos("a@x.com", None, 14)
    finally:
        srv.shutdown(); srv.server_close()


def test_ponte_email_indisponivel_e_erro_tipado(tmp_path):
    with pytest.raises(ErroGoogleOAuth):
        PonteEmail(tmp_path / "nada.sock").lixeira("a@x.com", ["a1"])


def test_ambiente_com_socket_tem_a_fabrica_do_email(tmp_path, monkeypatch):
    srv = Servidor(tmp_path / "f.sock", {"google_email": _FalsaEmail()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "f.sock"))
        fonte = fontes_do_ambiente()["google_email"]()
        assert isinstance(fonte, PonteEmail) and fonte.enviados_recentes("a@x.com", 30) == ["bia@x.com"]
    finally:
        srv.shutdown(); srv.server_close()


def test_ponte_email_respondeu_a_cruza_e_valida_a_forma(sock_email):
    p = PonteEmail(sock_email)
    assert p.respondeu_a("a@x.com", ["bia@x.com", "c@y.com"]) == {"bia@x.com": True, "c@y.com": False}
    with pytest.raises(ErroGoogleOAuth) as e:
        p.respondeu_a("malformada@x.com", ["bia@x.com"])
    assert "resposta inválida" in str(e.value)
    with pytest.raises(ErroGoogleOAuth) as e:
        p.respondeu_a("ruim@x.com", ["bia@x.com"])
    assert str(e.value) == "messages.list -> 500"


# ---- Graph da ness pela ponte ----
from gabi.fontes.graph_ness import ErroGraphNess  # noqa: E402
from gabi.fontes.ponte import PonteGraph  # noqa: E402


class _FalsoGraph:
    def contas(self):
        return ["resper@ness.com.br"]

    def contatos(self, conta):
        return [{"nome": "Ana", "telefone": "1"}]

    def listar_calendarios(self, conta):
        return [{"id": "A=", "nome": "Calendar", "principal": True}]

    def listar_eventos(self, conta, calendario_id, sync_token, janela):
        if conta == "malformada@x.com":
            return {"eventos": []}
        if conta == "boom@x.com":
            raise ErroGraphNess("GET /v1.0/users/x/calendarView/delta -> 401")
        return {"eventos": [{"externo_id": "a"}], "cancelados": ["b"], "novo_sync_token": "S", "recarga_completa": False}

    def teams_chats(self, conta):
        if conta == "malformada@x.com":
            return [{"chat_id": "c1", "tipo": "um_a_um"}]
        if conta == "texto@x.com":
            return [{"chat_id": "c1", "tipo": "grupo", "ultima_em": None, "corpo": "oi"}]
        return [{"chat_id": "c1", "tipo": "um_a_um", "ultima_em": "2026-10-20T10:00:00Z"}, {"chat_id": "c2", "tipo": "grupo", "ultima_em": None}]

    def teams_mensagens(self, conta, chat_id, desde):
        if conta == "malformada@x.com":
            return [{"id": "m1", "quando": "2026-10-20T10:00:00Z", "de_nome": "Ana", "de_eu": "sim", "mencoes_eu": False}]
        if conta == "naolista@x.com":
            return {"id": "m1"}
        return [{"id": "m1", "quando": "2026-10-20T10:00:00Z", "de_nome": "Ana", "de_eu": False, "mencoes_eu": True}]

    def contato_criar(self, conta, nome, telefone):
        return {"id": "AAMkAGI2TG93AAA="} if conta != "malformada@x.com" else {"id": 7}

    def contato_corrigir(self, conta, graph_id, antes, depois):
        if conta == "malformada@x.com":
            return {"resultado": "talvez"}
        return {"resultado": "ok" if antes == {"nome": "A", "telefone": "1"} and depois["nome"] == "B" else "alterado"}

    def contato_renomear(self, conta, graph_id, nome_antes, nome_depois):
        return {"resultado": "talvez"} if conta == "malformada@x.com" else {"resultado": "ok" if nome_antes == "A⁹" and nome_depois == "A" else "alterado"}

    def contato_apagar_telefone(self, conta, graph_id, campo, telefone_antes):
        return {"resultado": "ok" if (campo, telefone_antes) == ("home", "1") else "alterado"}

    def contato_apagar(self, conta, graph_id, nome_antes, telefone_antes):
        return {"resultado": "ok" if nome_antes == "U" else "alterado"}

    def contato_adicionar_email(self, conta, graph_id, nome_antes, telefone_antes, emails):
        return {"resultado": "ok" if (nome_antes, telefone_antes, emails) == ("U", "1", ["a@x.com"]) else "alterado"}

    def evento_criar(self, conta, chave, evento):
        return {"externo_id": 7} if conta == "malformada@x.com" else {"externo_id": "AAMkEVT=", "eco": evento["titulo"] == "T"}

    def teams_equipes(self, conta):
        return [{"id": "e1"}] if conta == "malformada@x.com" else [{"id": "e1", "nome": "Comercial"}]

    def teams_canais(self, conta, equipe_id):
        return {"id": "c1"} if conta == "malformada@x.com" else [{"id": "c1", "nome": f"Geral de {equipe_id}"}]

    def teams_chat_enviar(self, conta, chat_id, texto):
        return {} if conta == "malformada@x.com" else {"externo_id": f"m-{chat_id}-{texto}"}

    def teams_canal_enviar(self, conta, equipe_id, canal_id, texto):
        return {"externo_id": None} if conta == "malformada@x.com" else {"externo_id": f"m-{equipe_id}-{canal_id}-{texto}"}

    def enviar(self):
        return "nunca"


@pytest.fixture
def sock_graph(tmp_path):
    srv = Servidor(tmp_path / "gr.sock", {"graph_ness": _FalsoGraph(), "paperless": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path / "gr.sock"
    srv.shutdown(); srv.server_close()


def test_graph_ness_metodos_permitidos(sock_graph):
    assert PERMITIDOS["graph_ness"] == frozenset({"contas", "contatos", "listar_calendarios", "listar_eventos", "listar_novos", "lixeira", "restaurar",
                                                  "enviados_recentes", "respondeu_a", "teams_chats", "teams_mensagens",
                                                  "contato_criar", "contato_corrigir", "contato_renomear", "contato_apagar_telefone", "contato_apagar", "contato_adicionar_email",
                                                  "evento_criar", "teams_equipes", "teams_canais", "teams_chat_enviar", "teams_canal_enviar"})
    assert ERROS["graph_ness"] is ErroGraphNess
    with pytest.raises(ErroGraphNess, match="metodo_proibido"):
        Ponte(sock_graph, "graph_ness")._chamar("enviar")


def test_ponte_graph_cruza_resultados(sock_graph):
    p = PonteGraph(sock_graph)
    assert p.configurada() and p.contas() == ["resper@ness.com.br"]
    assert p.contatos("resper@ness.com.br") == [{"nome": "Ana", "telefone": "1"}]
    assert p.listar_calendarios("resper@ness.com.br")[0]["principal"] is True
    r = p.listar_eventos("resper@ness.com.br", "primary", None, JANELA_AG)
    assert isinstance(r, ResultadoEventos) and r.cancelados == ["b"] and r.novo_sync_token == "S"


def test_ponte_graph_valida_forma(sock_graph):
    with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
        PonteGraph(sock_graph).listar_eventos("malformada@x.com", "primary", None, JANELA_AG)
    with pytest.raises(ErroGraphNess, match="-> 401"):
        PonteGraph(sock_graph).listar_eventos("boom@x.com", "primary", None, JANELA_AG)


def test_ponte_graph_contato_escrita_cruza_dicts_e_valida_forma(sock_graph):
    p = PonteGraph(sock_graph)
    assert p.contato_criar("resper@ness.com.br", "A", "1") == {"id": "AAMkAGI2TG93AAA="}
    assert p.contato_corrigir("resper@ness.com.br", "AAMkAGI2TG93AAA=", {"nome": "A", "telefone": "1"}, {"nome": "B", "telefone": "2"}) == {"resultado": "ok"}
    with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
        p.contato_criar("malformada@x.com", "A", "1")
    with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
        p.contato_corrigir("malformada@x.com", "AAMkAGI2TG93AAA=", {}, {})


def test_ponte_graph_envios_cruzam_e_validam_forma(sock_graph):
    p = PonteGraph(sock_graph)
    assert p.evento_criar("resper@ness.com.br", "0123456789abcdefghijklmnop", {"titulo": "T"}) == {"externo_id": "AAMkEVT=", "eco": True}
    assert p.teams_equipes("resper@ness.com.br") == [{"id": "e1", "nome": "Comercial"}]
    assert p.teams_canais("resper@ness.com.br", "e1") == [{"id": "c1", "nome": "Geral de e1"}]
    assert p.teams_chat_enviar("resper@ness.com.br", "19:a", "oi") == {"externo_id": "m-19:a-oi"}
    assert p.teams_canal_enviar("resper@ness.com.br", "e1", "19:c", "oi") == {"externo_id": "m-e1-19:c-oi"}
    for chamar in (lambda: p.evento_criar("malformada@x.com", "k", {"titulo": "T"}), lambda: p.teams_equipes("malformada@x.com"),
                   lambda: p.teams_canais("malformada@x.com", "e1"), lambda: p.teams_chat_enviar("malformada@x.com", "19:a", "oi"),
                   lambda: p.teams_canal_enviar("malformada@x.com", "e1", "19:c", "oi")):
        with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
            chamar()


def test_ponte_graph_nao_configurada(tmp_path):
    srv = Servidor(tmp_path / "n.sock", {"graph_ness": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert PonteGraph(tmp_path / "n.sock").configurada() is False
    finally:
        srv.shutdown(); srv.server_close()


def test_ambiente_com_socket_expoe_graph_ness(tmp_path, monkeypatch):
    srv = Servidor(tmp_path / "e.sock", {"graph_ness": _FalsoGraph()})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GABI_FONTES_SOCKET", str(tmp_path / "e.sock"))
        assert isinstance(fontes_do_ambiente()["graph_ness"](), PonteGraph)
    finally:
        srv.shutdown(); srv.server_close()


def test_ponte_do_graph_aceita_o_correio_e_valida_a_forma_com_o_erro_da_ness(tmp_path):
    from gabi.fontes.graph_ness import ErroGraphNess
    assert {"listar_novos", "lixeira", "restaurar", "enviados_recentes", "respondeu_a"} <= PERMITIDOS["graph_ness"]
    for proibido in ("enviar", "apagar", "send", "delete", "responder"):
        assert proibido not in PERMITIDOS["graph_ness"]

    class Falsa(_FalsaEmail):
        pass
    srv = Servidor(tmp_path / "gm.sock", {"graph_ness": Falsa(), "paperless": None})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = PonteEmail(tmp_path / "gm.sock", "graph_ness", ErroGraphNess)
        assert p.configurada()
        assert p.listar_novos("a@x.com", None, 14).novo_history_id == "H"
        assert p.lixeira("a@x.com", ["a1"]) == {"a1": "ok"}
        with pytest.raises(ErroGraphNess, match="resposta inválida"):
            p.listar_novos("malformada@x.com", None, 14)
        with pytest.raises(ErroGraphNess, match="resposta inválida"):
            p.lixeira("malformada@x.com", ["a1"])
        with pytest.raises(ErroGraphNess, match="resposta inválida"):
            p.enviados_recentes("malformada@x.com", 365)
    finally:
        srv.shutdown(); srv.server_close()


def test_teams_metodos_estao_permitidos():
    assert {"teams_chats", "teams_mensagens"} <= PERMITIDOS["graph_ness"]


def test_escrita_do_teams_e_so_a_dos_envios_aprovados():
    import re
    # ADR-024: só escrever em chat existente e postar em canal, com proposta aprovada; responder, apagar e reagir continuam fora
    assert {m for m in PERMITIDOS["graph_ness"] if m.startswith("teams") and re.search(r"enviar|responder|apagar|reagir", m)} == {
        "teams_chat_enviar", "teams_canal_enviar"}  # apagar de CONTATO é da ADR-021


def test_ponte_graph_teams_chats_valida_forma(sock_graph):
    p = PonteGraph(sock_graph)
    r = p.teams_chats("resper@ness.com.br")
    assert [c["chat_id"] for c in r] == ["c1", "c2"] and r[1]["ultima_em"] is None
    for conta in ("malformada@x.com", "texto@x.com"):
        with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
            p.teams_chats(conta)


def test_ponte_graph_teams_mensagens_valida_forma(sock_graph):
    p = PonteGraph(sock_graph)
    r = p.teams_mensagens("resper@ness.com.br", "c1", "2026-10-19T00:00:00Z")
    assert r == [{"id": "m1", "quando": "2026-10-20T10:00:00Z", "de_nome": "Ana", "de_eu": False, "mencoes_eu": True}]
    for conta in ("malformada@x.com", "naolista@x.com"):
        with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
            p.teams_mensagens(conta, "c1", "2026-10-19T00:00:00Z")


def test_cliente_graph_limpeza_ida_e_volta_e_resposta_invalida(sock_graph):
    p = PonteGraph(sock_graph)
    assert p.contato_renomear("resper@ness.com.br", "AAMkAGI2TG93AAA=", "A⁹", "A") == {"resultado": "ok"}
    assert p.contato_apagar_telefone("resper@ness.com.br", "AAMkAGI2TG93AAA=", "home", "1") == {"resultado": "ok"}
    assert p.contato_apagar("resper@ness.com.br", "AAMkAGI2TG93AAA=", "X", "1") == {"resultado": "alterado"}
    assert p.contato_adicionar_email("resper@ness.com.br", "AAMkAGI2TG93AAA=", "U", "1", ["a@x.com"]) == {"resultado": "ok"}
    with pytest.raises(ErroGraphNess, match="resposta inválida do serviço de fontes"):
        p.contato_renomear("malformada@x.com", "AAMkAGI2TG93AAA=", "A", "B")


def test_nibo_e_paperless_so_leitura_que_tem_uso():
    """ADR-023: lote do Nibo, comprovantes e reembolso saíram; a ponte não pode mais deixar ninguém escrever no Nibo nem no Paperless (R2)."""
    assert PERMITIDOS["nibo"] == frozenset({"nfse", "agendamentos_a_receber", "obter_arquivo"})
    assert PERMITIDOS["paperless"] == frozenset({"docs", "baixar", "texto", "documento"})


def test_ponte_agenda_evento_criar_cruza_e_valida_a_forma(sock_agenda):
    p = PonteAgenda(sock_agenda)
    assert p.evento_criar("a@x.com", "0123456789abcdefghijklmnop", {"titulo": "t"}) == {"externo_id": "0123456789abcdefghijklmnop", "ja_existia": False}
    for conta in ("malformada@x.com", "faltando@x.com"):
        with pytest.raises(ErroGoogleOAuth) as e:
            p.evento_criar(conta, "0123456789abcdefghijklmnop", {})
        assert str(e.value) == "resposta inválida do serviço de fontes"
