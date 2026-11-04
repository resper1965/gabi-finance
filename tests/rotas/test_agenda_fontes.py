import json

import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.fontes.google_oauth import ErroGoogleOAuth
from gabi.fontes.graph_ness import ErroGraphNess

from tests.rotas.test_contatos import AGORA, BOSS, JSON, VIP, banco  # noqa: F401  (fixture banco)

U = "/api/v1/agenda"


class _Agenda:
    def __init__(self, cals=None, erro=None):
        self.cals, self.erro, self.chamadas = cals or [], erro, []

    def listar_calendarios(self, conta):
        self.chamadas.append(conta)
        if self.erro:
            raise self.erro
        return self.cals


def _cli(banco, fonte=None):
    fontes = {"google_agenda": (lambda: fonte)} if fonte is not None else {}
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes=fontes), client=("127.0.0.1", 50000))


@pytest.fixture
def cli(banco):
    return _cli(banco, _Agenda([{"id": "resper@gmail.com", "nome": "Ricardo", "principal": True}, {"id": "fam@group.calendar.google.com", "nome": "Família", "principal": False}]))


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _patch(cli, url, corpo, h=BOSS):
    return cli.patch(url, headers={**h, **JSON}, content=json.dumps(corpo))


def _put(cli, corpo, h=BOSS):
    return cli.put(f"{U}/parametros", headers={**h, **JSON}, content=json.dumps(corpo))


def _criar(cli, conta="resper@gmail.com", **kw):
    r = _post(cli, f"{U}/fontes", {"conta": conta, "provedor": "google", **kw})
    assert r.status_code == 200, r.text
    return r.json()["dados"]["id"]


def _decisoes(banco):
    c = conectar(banco)
    r = [x["o_que"] for x in c.execute("select o_que from decisao order by id")]
    c.close()
    return r


def test_so_boss_acessa(cli):
    for m, url in (("get", f"{U}/fontes"), ("post", f"{U}/fontes"), ("post", f"{U}/fontes/1/calendarios/descobrir"), ("patch", f"{U}/fontes/1"),
                   ("get", f"{U}/parametros"), ("put", f"{U}/parametros")):
        assert getattr(cli, m)(url, headers=VIP).status_code == 403, (m, url)
        assert getattr(cli, m)(url).status_code == 401, (m, url)


def test_criar_fonte_valida_email_e_provedor(cli, banco):
    assert _post(cli, f"{U}/fontes", {"conta": "isto-nao-e-email", "provedor": "google"}).status_code == 400
    assert _post(cli, f"{U}/fontes", {"conta": "a@x.com", "provedor": "outlook"}).status_code == 400
    assert _post(cli, f"{U}/fontes", {"conta": "a@x.com", "provedor": "google", "auth": "senha"}).status_code == 400
    assert _post(cli, f"{U}/fontes", []).status_code == 400
    fid = _criar(cli, "a@x.com")
    f = cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"]
    assert [(x["id"], x["conta"], x["estado"], x["provedor"], x["calendario_id"], x["eventos"]) for x in f] == [(fid, "a@x.com", "a_decidir", "google", "primary", 0)]
    assert _post(cli, f"{U}/fontes", {"conta": "a@x.com", "provedor": "google"}).status_code == 409
    assert _post(cli, f"{U}/fontes", {"conta": "g@x.com", "provedor": "graph", "auth": "delegacao"}).status_code == 200


def test_descobrir_calendarios_cria_fontes_a_decidir(cli, banco):
    fid = _criar(cli)
    r = _post(cli, f"{U}/fontes/{fid}/calendarios/descobrir")
    assert r.status_code == 200, r.text
    cals = r.json()["dados"]["calendarios"]
    assert [(c["calendario_id"], c["nome"], c["estado"], c["nova"]) for c in cals] == [("primary", "Ricardo", "a_decidir", False), ("fam@group.calendar.google.com", "Família", "a_decidir", True)]
    fontes = cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"]
    assert len(fontes) == 2
    # de novo: não duplica e não mexe no estado já decidido
    _patch(cli, f"{U}/fontes/{fid}", {"estado": "sim"})
    cals = _post(cli, f"{U}/fontes/{fid}/calendarios/descobrir").json()["dados"]["calendarios"]
    assert [c["nova"] for c in cals] == [False, False] and cals[0]["estado"] == "sim"
    assert len(cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"]) == 2


def test_descobrir_em_fonte_inexistente(cli):
    assert _post(cli, f"{U}/fontes/999/calendarios/descobrir").status_code == 404


class _Graph:
    def __init__(self, cals=None, erro=None):
        self.cals, self.erro, self.chamadas = cals or [], erro, []

    def listar_calendarios(self, conta):
        self.chamadas.append(conta)
        if self.erro:
            raise self.erro
        return self.cals


def _cli_graph(banco, graph=None):
    fontes = {"graph_ness": (lambda: graph)} if graph is not None else {}
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes=fontes), client=("127.0.0.1", 50000))


def test_descobrir_calendarios_do_graph(banco):
    graph = _Graph([{"id": "AAA=", "nome": "Calendar", "principal": True}, {"id": "BBB=", "nome": "Feriados", "principal": False}])
    cli = _cli_graph(banco, graph)
    gid = _criar(cli, "resper@ness.com.br", provedor="graph")
    r = _post(cli, f"{U}/fontes/{gid}/calendarios/descobrir")
    assert r.status_code == 200, r.text
    assert [(c["calendario_id"], c["nome"], c["estado"]) for c in r.json()["dados"]["calendarios"]] == [("primary", "Calendar", "a_decidir"), ("BBB=", "Feriados", "a_decidir")]
    assert graph.chamadas == ["resper@ness.com.br"]


def test_descobrir_graph_sem_fonte_ou_com_ponte_fora_vira_503(banco):
    sem = _cli_graph(banco)
    gid = _criar(sem, "resper@ness.com.br", provedor="graph")
    r = _post(sem, f"{U}/fontes/{gid}/calendarios/descobrir")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    caida = _cli_graph(banco, _Graph(erro=ErroGraphNess("serviço de fontes indisponível")))
    r = _post(caida, f"{U}/fontes/{gid}/calendarios/descobrir")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def test_ponte_fora_vira_503(banco):
    sem_fonte = _cli(banco)  # fonte não configurada
    fid = _criar(sem_fonte)
    r = _post(sem_fonte, f"{U}/fontes/{fid}/calendarios/descobrir")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    caida = _cli(banco, _Agenda(erro=ErroGoogleOAuth("serviço de fontes indisponível")))
    r = _post(caida, f"{U}/fontes/{fid}/calendarios/descobrir")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    assert len(caida.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"]) == 1  # nada foi criado


def test_liberar_fonte_muda_estado(cli, banco):
    fid = _criar(cli)
    for estado in ("sim", "nao", "a_decidir"):
        assert _patch(cli, f"{U}/fontes/{fid}", {"estado": estado}).status_code == 200
        assert cli.get(f"{U}/fontes", headers=BOSS).json()["dados"]["fontes"][0]["estado"] == estado
    assert _patch(cli, f"{U}/fontes/{fid}", {"estado": "talvez"}).status_code == 400
    assert _patch(cli, f"{U}/fontes/{fid}", {}).status_code == 400
    assert _patch(cli, f"{U}/fontes/999", {"estado": "sim"}).status_code == 404
    assert any(f"fonte {fid} → sim" in d for d in _decisoes(banco))


def test_parametros_padrao_e_gravacao(cli):
    assert cli.get(f"{U}/parametros", headers=BOSS).json()["dados"] == {"privados": "mostrar", "fuso": "America/Sao_Paulo", "janela_passado_dias": 7, "janela_futuro_dias": 90}
    r = _put(cli, {"privados": "so_painel", "janela_futuro_dias": 120})
    assert r.status_code == 200 and r.json()["dados"]["privados"] == "so_painel" and r.json()["dados"]["janela_futuro_dias"] == 120
    assert cli.get(f"{U}/parametros", headers=BOSS).json()["dados"]["privados"] == "so_painel"


@pytest.mark.parametrize("corpo", [{}, {"privados": "tudo"}, {"fuso": "Marte/Olimpo"}, {"fuso": 3}, {"janela_passado_dias": 61}, {"janela_passado_dias": -1},
                                   {"janela_futuro_dias": 6}, {"janela_futuro_dias": 366}, {"janela_futuro_dias": "90"}, {"janela_futuro_dias": True}, {"outra": 1}])
def test_parametros_validam_faixas(cli, corpo):
    assert _put(cli, corpo).status_code == 400
    assert cli.get(f"{U}/parametros", headers=BOSS).json()["dados"]["privados"] == "mostrar"


def test_parametros_nao_logam_valores(cli, banco):
    _put(cli, {"privados": "ocultar", "fuso": "America/Bahia"})
    d = " | ".join(_decisoes(banco))
    assert "agenda.fuso" in d and "agenda.privados" in d and "ocultar" not in d and "Bahia" not in d


def test_a_politica_gravada_vale_para_a_leitura(cli, banco):
    c = conectar(banco)
    c.execute("insert into agenda_fonte(id, conta, provedor, estado) values (7,'a@x.com','google','sim')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo, privado) values (7,'p','2026-10-16T13:00:00+00:00','2026-10-16T14:00:00+00:00','2026-10-16','2026-10-16','Médico',1)")
    c.close()
    ver = lambda: cli.get(f"{U}?de=2026-10-16&ate=2026-10-16", headers=BOSS).json()["dados"]["eventos"][0]["titulo"]  # noqa: E731
    assert ver() == "Médico"
    _put(cli, {"privados": "ocultar"})
    assert ver() == "Compromisso privado"


def test_mudar_parametro_forca_recarga_completa_na_proxima_rodada(cli, banco):
    c = conectar(banco)
    c.execute("insert into agenda_fonte(id, conta, provedor, estado, sync_token, recarga_em) values (7,'a@x.com','google','sim','T','2026-10-16T10:00:00+00:00')")
    c.close()
    assert _put(cli, {"privados": "so_painel"}).status_code == 200
    c = conectar(banco)
    linha = c.execute("select sync_token, recarga_em from agenda_fonte where id=7").fetchone()
    c.close()
    assert linha["recarga_em"] is None  # dia_local, título mascarado e janela foram calculados com o valor antigo: refaz tudo
    assert _put(cli, {"privados": "inexistente"}).status_code == 400  # pedido inválido não força nada


def test_descobrir_nao_trava_o_laco_da_api_e_404_vem_antes_do_503(banco):
    import asyncio
    ag = _Agenda([{"id": "resper@gmail.com", "nome": "Ricardo", "principal": True}])
    original = ag.listar_calendarios
    ag.no_laco = None

    def listar(conta):
        try:
            asyncio.get_running_loop()
            ag.no_laco = True  # a chamada de rede bloqueante rodou dentro do laço de eventos
        except RuntimeError:
            ag.no_laco = False
        return original(conta)
    ag.listar_calendarios = listar
    cli = _cli(banco, ag)
    fid = _criar(cli)
    assert _post(cli, f"{U}/fontes/{fid}/calendarios/descobrir").status_code == 200
    assert ag.no_laco is False
    sem_fonte = _cli(banco)
    assert _post(sem_fonte, f"{U}/fontes/999/calendarios/descobrir").status_code == 404  # fonte inexistente: 404 antes do 503


def test_conta_e_normalizada_para_minusculas_e_nao_duplica(cli, banco):
    """Agenda M9: Resper@Gmail.com e resper@gmail.com são a mesma conta."""
    fid = _criar(cli, "Resper@Gmail.COM")
    c = conectar(banco)
    assert c.execute("select conta from agenda_fonte where id=?", (fid,)).fetchone()[0] == "resper@gmail.com"
    c.close()
    r = _post(cli, f"{U}/fontes", {"conta": "resper@gmail.com", "provedor": "google"})
    assert r.status_code == 409


def test_desligar_ou_devolver_para_decisao_limpa_o_ultimo_erro(cli, banco):
    fid = _criar(cli)
    c = conectar(banco)
    c.execute("update agenda_fonte set ultimo_erro='calendar.events.list -> 500', estado='sim' where id=?", (fid,))
    c.commit()
    c.close()
    assert _patch(cli, f"{U}/fontes/{fid}", {"estado": "nao"}).status_code == 200
    c = conectar(banco)
    assert c.execute("select ultimo_erro from agenda_fonte where id=?", (fid,)).fetchone()[0] is None
    c.close()
