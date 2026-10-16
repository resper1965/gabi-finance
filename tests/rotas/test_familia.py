
import pytest
from fastapi.testclient import TestClient

from gabi.api import criar_app
from gabi.db import conectar
from gabi.familia.saude import abrir_saude
from gabi.familia.exames import versoes
from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, get, post  # noqa: F401  (fixtures)

CHAVE = bytes(range(32))
LAUDO = "Paciente: Ana   Data da coleta: 10/07/2026\nColesterol total ... 215 mg/dL Valor de referência: 0 a 200 mg/dL\nGlicose: 92 mg/dL\n"


LAUDO2 = "Paciente: Ana   Data da coleta: 11/08/2026\nHemoglobina 13,5 g/dL\n"
CONTEUDOS = {55: LAUDO, 56: LAUDO2}  # compartilhado entre instâncias: o teste troca o texto para simular um reprocessamento


class PaperlessFalso:
    def __init__(self):
        self.pedidos = []

    def docs(self, **f):
        self.pedidos.append(f)
        return [{"id": f["id"], "content": CONTEUDOS[f["id"]], "created": "2026-07-11T10:00:00-03:00"}] if f.get("id") in CONTEUDOS else []

    def baixar(self, id):
        return b"%PDF"


@pytest.fixture(autouse=True)
def _conteudos():
    antigo = dict(CONTEUDOS)
    yield
    CONTEUDOS.clear()
    CONTEUDOS.update(antigo)


@pytest.fixture
def app(banco, tmp_path):
    c = conectar(banco)
    c.execute("insert into matriz_acesso(informacao, boss, familia_vip, terceiros) values ('saúde','total','parcial','nenhum')")
    c.execute("insert into pessoa(id, nome) values ('p2','Maria')")
    c.close()
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"paperless": lambda: PaperlessFalso()})
    a.state.saude = (tmp_path / "saude.enc", CHAVE)
    return a


@pytest.fixture
def cli(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def _semear(app):
    with abrir_saude(*app.state.saude) as s:
        from gabi.familia.saude import registrar_exame
        import datetime as dt
        registrar_exame(s, "p2", "Colesterol total", "190", "mg/dL", dt.date(2026, 1, 1), ("0", "200"), 1, "boss@x.com")  # p2 = vip@x.com
        registrar_exame(s, "p9", "Colesterol total", "150", "mg/dL", dt.date(2026, 1, 1), ("0", "200"), 2, "boss@x.com")


def test_sem_chave_configurada_da_503(banco):
    a = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={})
    a.state.saude = None
    r = TestClient(a, client=("127.0.0.1", 50000)).get("/api/v1/familia/pessoas", headers=BOSS)
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def test_boss_ve_todas_as_pessoas_e_o_familiar_so_a_propria(app, cli):
    _semear(app)
    assert {p["id"] for p in get(cli, "/api/v1/familia/pessoas").json()["dados"]["itens"]} == {"p1", "p2", "p9"}
    assert {p["id"] for p in get(cli, "/api/v1/familia/pessoas", VIP).json()["dados"]["itens"]} == {"p2"}


def test_familiar_nao_ve_pasta_de_outro(app, cli):
    _semear(app)
    assert get(cli, "/api/v1/familia/exames/p2", VIP).status_code == 200
    assert get(cli, "/api/v1/familia/exames/p9", VIP).status_code == 403
    assert get(cli, "/api/v1/familia/exames/p9/serie?marcador=Colesterol total", VIP).status_code == 403
    assert get(cli, "/api/v1/familia/exames/p9/resumo", VIP).status_code == 403


def test_terceiro_e_quem_nao_tem_matriz_nao_alcancam(app, cli, banco):
    c = conectar(banco)
    c.execute("update matriz_acesso set familia_vip='nenhum'")
    c.close()
    assert get(cli, "/api/v1/familia/exames/p2", VIP).status_code == 403
    assert cli.get("/api/v1/familia/pessoas").status_code == 401


def test_marcadores_serie_e_resumo_do_boss(app, cli):
    _semear(app)
    d = get(cli, "/api/v1/familia/exames/p2").json()["dados"]
    assert d["marcadores"][0]["marcador"] == "Colesterol total" and d["marcadores"][0]["valor"] == "190"
    s = get(cli, "/api/v1/familia/exames/p2/serie?marcador=Colesterol total").json()["dados"]
    assert [p["valor"] for p in s["pontos"]] == ["190"] and s["pontos"][0]["fora_da_faixa"] is False
    assert "Colesterol total" in get(cli, "/api/v1/familia/exames/p2/resumo").json()["dados"]["texto"]


def test_leitura_pela_api_fica_registrada_com_o_login(app, cli):
    _semear(app)
    get(cli, "/api/v1/familia/exames/p2/resumo", VIP)
    with abrir_saude(*app.state.saude) as s:
        assert ("vip@x.com", "p2", "resumo") in [tuple(r) for r in s.con.execute("select quem, pessoa_id, o_que from leitura")]


def test_fluxo_de_laudo_ler_confirmar_e_aparecer(app, cli):
    r = post(cli, "/api/v1/familia/laudos", {"paperless_id": 55, "pessoa_sugerida": "p2"})
    assert r.status_code == 201 and r.json()["dados"]["propostas"] == 2
    assert get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"] == []  # só proposta
    pend = get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"]
    assert pend[0]["paperless_id"] == 55 and {m["marcador"] for m in pend[0]["marcadores"]} == {"Colesterol total", "Glicose"}
    assert post(cli, "/api/v1/familia/laudos/55/confirmar", {}).status_code == 400  # sem a pessoa
    assert post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"}).json()["dados"]["exames"] == 2
    assert len(get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"]) == 2


def test_laudo_e_so_do_boss_e_documento_inexistente_da_404(app, cli):
    assert post(cli, "/api/v1/familia/laudos", {"paperless_id": 55}, VIP).status_code == 403
    assert post(cli, "/api/v1/familia/laudos", {"paperless_id": 999}).status_code == 404


def test_rejeitar_laudo_descarta(app, cli):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    assert post(cli, "/api/v1/familia/laudos/55/rejeitar", {}).json()["dados"]["rejeitadas"] == 2
    assert get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"] == []


def test_edicoes_externas_listar_e_decidir(app, cli, banco):
    c = conectar(banco)
    c.execute("insert into edicao_externa(pessoa_id, arquivo, texto, hash, criado_em) values ('p1','Frentes.md','novo','h','2026-10-10T10:00:00+00:00')")
    c.close()
    assert get(cli, "/api/v1/familia/edicoes", VIP).status_code == 403
    assert [e["arquivo"] for e in get(cli, "/api/v1/familia/edicoes").json()["dados"]["itens"]] == ["Frentes.md"]
    assert post(cli, "/api/v1/familia/edicoes/1/decidir", {"estado": "talvez"}).status_code == 400
    assert post(cli, "/api/v1/familia/edicoes/1/decidir", {"estado": "rejeitada"}).status_code == 200
    assert get(cli, "/api/v1/familia/edicoes").json()["dados"]["itens"] == []
    assert post(cli, "/api/v1/familia/edicoes/1/decidir", {"estado": "aprovada"}).status_code == 404


def _estado(banco, pid):
    c = conectar(banco)
    try:
        r = c.execute("select estado, versao from exame_doc where paperless_id=?", (pid,)).fetchone()
        return tuple(r) if r else None
    finally:
        c.close()


def test_lote_confirma_varios_documentos(app, cli, banco):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 56})
    assert _estado(banco, 55) == ("extraido", 1)
    r = post(cli, "/api/v1/familia/laudos/lote", {"itens": [{"paperless_id": 55, "pessoa_id": "p2"}, {"paperless_id": 56, "pessoa_id": "p2"}]})
    assert r.status_code == 200 and r.json()["dados"] == {"confirmados": 2, "exames": 3}
    assert {m["marcador"] for m in get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"]} == {"Colesterol total", "Glicose", "Hemoglobina"}
    assert _estado(banco, 55)[0] == "confirmado" and _estado(banco, 56)[0] == "confirmado"
    assert get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"] == []


def test_lote_e_atomico(app, cli, banco):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    for itens in ([{"paperless_id": 55, "pessoa_id": "p2"}, {"paperless_id": 999, "pessoa_id": "p2"}],   # sem propostas
                  [{"paperless_id": 55, "pessoa_id": "p2"}, {"paperless_id": 56, "pessoa_id": "naoexiste"}],  # pessoa desconhecida
                  [{"paperless_id": 55, "pessoa_id": "p2"}, {"paperless_id": 55, "pessoa_id": "p2"}], []):
        assert post(cli, "/api/v1/familia/laudos/lote", {"itens": itens}).status_code == 400
    assert get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"] == []
    assert [l["paperless_id"] for l in get(cli, "/api/v1/familia/laudos").json()["dados"]["itens"]] == [55]
    assert _estado(banco, 55) == ("extraido", 1)


def test_reprocessar_por_filtro_e_por_documento(app, cli, banco):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"})
    assert post(cli, "/api/v1/familia/exames/reprocessar", {}).status_code == 400
    r = post(cli, "/api/v1/familia/exames/reprocessar", {"pessoa_id": "p2"}).json()["dados"]
    assert r == {"documentos": 1, "versoes_novas": 0, "diferentes": 0, "falhos": 0, "restantes": 0}  # nada mudou: nenhuma versão nova
    CONTEUDOS[55] = LAUDO.replace("215", "180")
    r = post(cli, "/api/v1/familia/exames/reprocessar", {"pessoa_id": "p2"}).json()["dados"]
    assert (r["versoes_novas"], r["diferentes"], r["falhos"]) == (1, 1, 0)
    assert [p["valor"] for p in get(cli, "/api/v1/familia/exames/p2/serie?marcador=Colesterol total").json()["dados"]["pontos"]] == ["180"]
    assert _estado(banco, 55) == ("confirmado", 2)
    d = get(cli, "/api/v1/familia/exames/p2/laudos/55/versoes").json()["dados"]
    assert [v["versao"] for v in d["versoes"]] == [1, 2] and d["diferencas"][0]["antes"] == "215" and d["diferencas"][0]["depois"] == "180"
    assert post(cli, "/api/v1/familia/exames/reprocessar", {"paperless_id": 55}).json()["dados"]["documentos"] == 1
    assert post(cli, "/api/v1/familia/exames/reprocessar", {"todos": True}).json()["dados"]["documentos"] == 1


def test_reprocessar_documento_que_sumiu_do_paperless_conta_falho_e_mantem_os_dados(app, cli):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"})
    del CONTEUDOS[55]
    r = post(cli, "/api/v1/familia/exames/reprocessar", {"paperless_id": 55}).json()["dados"]
    assert r["falhos"] == 1 and r["versoes_novas"] == 0
    assert len(get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"]) == 2


def test_apelidos_e_reaplicar(app, cli):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"})
    r = cli.put("/api/v1/familia/marcadores/apelidos", json={"apelido": "Glicose", "marcador": "Glicemia"}, headers=BOSS)
    assert r.status_code == 200 and r.json()["dados"]["itens"] == [{"apelido": "glicose", "marcador": "Glicemia"}]
    assert cli.put("/api/v1/familia/marcadores/apelidos", json={"apelido": "", "marcador": "x"}, headers=BOSS).status_code == 400
    assert post(cli, "/api/v1/familia/marcadores/reaplicar", {}).json()["dados"]["alterados"] == 2  # a linha do exame e a da proposta confirmada
    assert {m["marcador"] for m in get(cli, "/api/v1/familia/exames/p2").json()["dados"]["marcadores"]} == {"Colesterol total", "Glicemia"}
    assert get(cli, "/api/v1/familia/marcadores/apelidos").json()["dados"]["itens"][0]["marcador"] == "Glicemia"


def test_parcial_recebe_403_nas_rotas_de_gestao(app, cli):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    for metodo, caminho, corpo in (("get", "/api/v1/familia/laudos", None), ("post", "/api/v1/familia/laudos/lote", {"itens": []}),
                                   ("post", "/api/v1/familia/exames/reprocessar", {"todos": True}), ("get", "/api/v1/familia/marcadores/apelidos", None),
                                   ("put", "/api/v1/familia/marcadores/apelidos", {"apelido": "a", "marcador": "b"}), ("post", "/api/v1/familia/marcadores/reaplicar", {}),
                                   ("get", "/api/v1/familia/exames/p2/laudos/55/versoes", None), ("get", "/api/v1/familia/laudos/contagem", None)):
        r = getattr(cli, metodo)(caminho, headers=VIP, **({"json": corpo} if corpo is not None else {}))
        assert r.status_code == 403, caminho


def test_contagem_nao_vaza_marcador_nem_nome(app, cli):
    assert get(cli, "/api/v1/familia/laudos/contagem").json()["dados"] == {"a_confirmar": 0}
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    r = get(cli, "/api/v1/familia/laudos/contagem")
    assert r.json()["dados"] == {"a_confirmar": 1}
    for proibido in ("Colesterol", "Glicose", "215", "Ana", "p2"):
        assert proibido not in r.text
    post(cli, "/api/v1/familia/laudos/55/confirmar", {"pessoa_id": "p2"})
    assert get(cli, "/api/v1/familia/laudos/contagem").json()["dados"] == {"a_confirmar": 0}


def test_rejeitar_marca_o_documento_descartado_e_documento_falho_aparece_com_motivo(app, cli, banco):
    post(cli, "/api/v1/familia/laudos", {"paperless_id": 55})
    post(cli, "/api/v1/familia/laudos/55/rejeitar", {})
    assert _estado(banco, 55)[0] == "descartado"
    c = conectar(banco)
    c.execute("insert into exame_doc(paperless_id, estado, motivo, atualizado_em) values (77, 'falhou', 'sem texto legível', 'x')")
    c.close()
    assert get(cli, "/api/v1/familia/laudos").json()["dados"]["falhos"] == [{"paperless_id": 77, "motivo": "sem texto legível"}]
