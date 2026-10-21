import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from gabi.acesso import adicionar
from gabi.api import criar_app
from gabi.db import conectar, migrar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
BOSS = {"Tailscale-User-Login": "boss@x.com"}
VIP = {"Tailscale-User-Login": "vip@x.com"}
JSON = {"Content-Type": "application/json"}
AGORA = dt.datetime(2026, 10, 16, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
N = "+5511912345678"
NQ = "%2B5511912345678"


@pytest.fixture
def banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    adicionar(c, "boss@x.com", "p1", "boss", por="t")
    adicionar(c, "vip@x.com", "p2", "familia_vip", por="t")
    c.execute("insert into rodada(fonte, inicio, fim, status, conferida) values ('open-finance','2026-10-16T11:00:00+00:00','2026-10-16T11:01:00+00:00','ok',1)")
    c.close()
    return p


@pytest.fixture
def cli(banco):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000))


def _pendente(banco, numero=N, nome="Joana"):
    c = conectar(banco)
    c.execute("insert into escuta_remetente(numero, nome, estado, vista_em, qtd) values (?,?, 'pendente', '2026-10-16T10:00:00+00:00', 2)", (numero, nome))
    c.close()


def _post(cli, url, corpo=None, h=BOSS):
    return cli.post(url, headers={**h, **JSON}, content=json.dumps(corpo if corpo is not None else {}))


def _put(cli, corpo, h=BOSS):
    return cli.put("/api/v1/escuta/parametros", headers={**h, **JSON}, content=json.dumps(corpo))


def _decisoes(banco):
    c = conectar(banco)
    r = [x["o_que"] for x in c.execute("select o_que from decisao order by id")]
    c.close()
    return r


from gabi.fontes.google_contatos import ErroGoogleContatos  # noqa: E402

GMAIL, NESS = "resper@gmail.com", "resper@ness.com.br"
U = "/api/v1/contatos"


class _Contatos:
    def __init__(self, dados=None, erro=None, falhas=None):
        self.dados, self.erro, self.falhas = dados or {}, erro, falhas or {}

    def listar(self, conta):
        if self.erro:
            raise self.erro
        if conta in self.falhas:
            raise self.falhas[conta]
        return self.dados.get(conta, [])


def _cli_contatos(banco, fonte):
    return TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"google_contatos": (lambda: fonte)}),
                      client=("127.0.0.1", 50000))


DADOS = {GMAIL: [{"nome": "Ana", "telefone": "(11) 91234-5678"}],
         NESS: [{"nome": "Zé", "telefone": "11 98888-7777"}, {"nome": "Ana ness", "telefone": "11912345678"}, {"nome": "Mau", "telefone": "12"}]}


@pytest.fixture
def cc(banco):
    return _cli_contatos(banco, _Contatos(DADOS))


def _sinc(cc):
    r = cc.post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 200, r.text
    return r.json()["dados"]


def test_contatos_so_boss(cc):
    for m, url in (("get", U), ("get", f"{U}/so-na-ness.csv"), ("post", f"{U}/sincronizar"), ("post", f"{U}/trazer"), ("delete", U)):
        assert getattr(cc, m)(url, headers=VIP).status_code == 403
        assert getattr(cc, m)(url).status_code == 401


def test_sincronizar_devolve_so_contagens(cc):
    d = _sinc(cc)
    assert d == {"contas": {GMAIL: {"lidos": 1}, NESS: {"lidos": 3}}, "total": 2, "invalidos": 1}


@pytest.mark.parametrize("fonte", [None, _Contatos(erro=ErroGoogleContatos("serviço de fontes indisponível"))])
def test_sincronizar_503_quando_a_ponte_cai_ou_nao_ha_fonte(banco, fonte):
    cli = _cli_contatos(banco, fonte)
    r = cli.post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"


def test_sincronizar_200_quando_uma_conta_falha_e_lista_a_falha_pelo_nome(banco):
    fonte = _Contatos(DADOS, falhas={NESS: ErroGoogleContatos(f"conta não autorizada: {NESS}")})
    r = _cli_contatos(banco, fonte).post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 200
    assert r.json()["dados"] == {"contas": {GMAIL: {"lidos": 1}, NESS: {"erro": f"conta não autorizada: {NESS}"}}, "total": 1, "invalidos": 0}


def test_sincronizar_503_quando_todas_as_contas_falham_e_nada_muda(banco):
    _sinc(_cli_contatos(banco, _Contatos(DADOS)))
    fonte = _Contatos(falhas={GMAIL: ErroGoogleContatos("serviço de fontes indisponível"), NESS: ErroGoogleContatos("serviço de fontes indisponível")})
    r = _cli_contatos(banco, fonte).post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 503 and r.json()["erro"] == "fonte_indisponivel"
    c = conectar(banco)
    assert c.execute("select count(*) from contato_google").fetchone()[0] == 3
    c.close()


def test_sincronizar_sem_chave_google_contatos_nas_fontes_e_503(banco):
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={}), client=("127.0.0.1", 50000))
    assert cli.post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}").status_code == 503


def test_listar_contatos_pagina_busca_e_ja_e_pessoa(cc, banco):
    _sinc(cc)
    c = conectar(banco)
    c.execute("insert into pessoa(id, nome, dados) values ('p9','Ana',?)", (json.dumps({"canais": ["whatsapp:+5511912345678"]}),))
    c.close()
    d = cc.get(U, headers=BOSS).json()["dados"]
    assert d["total"] == 2
    assert d["itens"] == [{"nome": "Ana", "telefone": "+5511912345678", "contas": [GMAIL, NESS], "ja_e_pessoa": True},
                          {"nome": "Zé", "telefone": "+5511988887777", "contas": [NESS], "ja_e_pessoa": False}]
    assert [i["nome"] for i in cc.get(f"{U}?busca=zé", headers=BOSS).json()["dados"]["itens"]] == ["Zé"]
    assert [i["nome"] for i in cc.get(f"{U}?busca=8888", headers=BOSS).json()["dados"]["itens"]] == ["Zé"]
    p = cc.get(f"{U}?limite=1&offset=1", headers=BOSS).json()["dados"]
    assert p["total"] == 2 and [i["nome"] for i in p["itens"]] == ["Zé"]


def test_csv_so_na_ness(cc):
    _sinc(cc)
    r = cc.get(f"{U}/so-na-ness.csv", headers=BOSS)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="contatos-so-na-ness.csv"'
    assert r.text == "Name,Phone 1 - Value\r\nZé,+5511988887777\r\n"


def test_csv_usa_as_contas_dos_parametros(cc, banco):
    _sinc(cc)
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('escuta.conta_origem_contatos', ?), ('escuta.conta_destino_contatos', ?)",
              (json.dumps(GMAIL), json.dumps(NESS)))
    c.close()
    assert cc.get(f"{U}/so-na-ness.csv", headers=BOSS).text == "Name,Phone 1 - Value\r\n"


def _trazer(cc, tels):
    return cc.post(f"{U}/trazer", headers={**BOSS, **JSON}, content=json.dumps({"telefones": tels}))


def test_trazer_cria_pessoa_sem_aprovar(cc, banco):
    _sinc(cc)
    r = _trazer(cc, ["+5511988887777", "+5511900000000", "lixo"])
    assert r.status_code == 200 and r.json()["dados"] == {"criadas": 1, "ignoradas": 2}
    c = conectar(banco)
    ps = c.execute("select nome, dados from pessoa").fetchall()
    assert len(ps) == 1 and ps[0]["nome"] == "Zé"
    d = json.loads(ps[0]["dados"])
    assert d == {"canais": ["whatsapp:+5511988887777"]}
    assert "escuta_aprovada" not in d and "pode_pedir" not in d
    o = [x for x in _decisoes(banco) if "trouxe" in x]
    assert len(o) == 1 and "9888" not in o[0] and "Zé" not in o[0]
    assert c.execute("select count(*) from escuta_remetente").fetchone()[0] == 0
    c.close()


def test_trazer_pula_quem_ja_e_pessoa_e_duplicados(cc, banco):
    _sinc(cc)
    c = conectar(banco)
    c.execute("insert into pessoa(id, nome, dados) values ('p9','Ana',?)", (json.dumps({"canais": ["whatsapp:11912345678"]}),))
    c.close()
    r = _trazer(cc, ["+5511912345678", "11 98888-7777", "+5511988887777"])
    assert r.json()["dados"] == {"criadas": 1, "ignoradas": 2}


@pytest.mark.parametrize("corpo", [{}, {"telefones": []}, {"telefones": "x"}, {"telefones": [1]}, {"telefones": ["+5511912345678"] * 101}])
def test_trazer_corpo_invalido_400(cc, corpo):
    r = cc.post(f"{U}/trazer", headers={**BOSS, **JSON}, content=json.dumps(corpo))
    assert r.status_code == 400


def test_trazer_100_cabe(cc, banco):
    _sinc(cc)
    assert _trazer(cc, ["+5511988887777"] * 100).json()["dados"] == {"criadas": 1, "ignoradas": 99}


def test_delete_apaga_tudo_e_audita(cc, banco):
    _sinc(cc)
    r = cc.delete(U, headers=BOSS)
    assert r.status_code == 200 and r.json()["dados"] == {"apagados": 3}
    c = conectar(banco)
    assert c.execute("select count(*) from contato_google").fetchone()[0] == 0
    c.close()
    assert sum("apagou contatos" in o for o in _decisoes(banco)) == 1
    assert cc.get(U, headers=BOSS).json()["dados"]["itens"] == []


def test_delete_apaga_tambem_os_emails_dos_contatos(cc, banco):
    _sinc(cc)
    c = conectar(banco)
    c.execute("insert into contato_google_email(conta, email, telefone, nome) values ('resper@gmail.com','a@x.com','+5511912345678','Ana')")
    c.close()
    assert cc.delete(U, headers=BOSS).status_code == 200
    c = conectar(banco)
    assert c.execute("select count(*) from contato_google_email").fetchone()[0] == 0
    c.close()


def test_trazer_e_depois_aprovar_resulta_em_uma_so_pessoa(cc, banco):
    _sinc(cc)
    assert _trazer(cc, ["+5511988887777"]).json()["dados"]["criadas"] == 1
    assert _post(cc, "/api/v1/escuta/remetentes/%2B5511988887777/aprovar", {"papel": "familia"}).status_code == 200
    c = conectar(banco)
    ps = c.execute("select id, dados from pessoa").fetchall()
    c.close()
    assert len(ps) == 1 and ps[0]["id"].startswith("wa-") and json.loads(ps[0]["dados"])["escuta_aprovada"] is True


def test_trazer_usa_o_mesmo_id_do_aprovar_e_reativa_pessoa_excluida_sem_aprovar(cc, banco):
    import hashlib
    _sinc(cc)
    pid = "wa-" + hashlib.sha1(b"+5511988887777").hexdigest()[:10]
    c = conectar(banco)
    c.execute("insert into pessoa(id, nome, dados, origem, excluido_em) values (?, 'Velho', ?, 'escuta', '2026-01-01')",
              (pid, json.dumps({"canais": ["whatsapp:+5511988887777"], "escuta_aprovada": True, "papel_escuta": "familia"})))
    c.close()
    assert _trazer(cc, ["+5511988887777"]).json()["dados"] == {"criadas": 1, "ignoradas": 0}
    c = conectar(banco)
    ps = c.execute("select id, excluido_em, dados from pessoa").fetchall()
    c.close()
    assert [p["id"] for p in ps] == [pid] and ps[0]["excluido_em"] is None
    assert json.loads(ps[0]["dados"]).get("escuta_aprovada") is not True


def test_openapi_documenta_o_csv_como_text_csv():
    spec = json.loads((Path(__file__).parent.parent.parent / "docs" / "openapi.json").read_text())
    assert "text/csv" in spec["paths"]["/api/v1/contatos/so-na-ness.csv"]["get"]["responses"]["200"]["content"]


class _GraphContatos:
    def __init__(self, contas, dados):
        self._contas, self.dados, self.pedidas = contas, dados, []

    def contas(self):
        return self._contas

    def contatos(self, conta):
        self.pedidas.append(conta)
        return self.dados.get(conta, [])


def test_sincronizar_manda_a_conta_da_ness_ao_graph(banco):
    google = _Contatos({GMAIL: [{"nome": "Ana", "telefone": "(11) 91234-5678"}]})
    graph = _GraphContatos([NESS], {NESS: [{"nome": "Zé", "telefone": "11 98888-7777"}]})
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA,
                               fontes={"google_contatos": (lambda: google), "graph_ness": (lambda: graph)}), client=("127.0.0.1", 50000))
    r = cli.post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 200, r.text
    assert r.json()["dados"]["contas"] == {GMAIL: {"lidos": 1}, NESS: {"lidos": 1}} and graph.pedidas == [NESS]


def test_sincronizar_so_com_o_graph_configurado(banco):
    graph = _GraphContatos([NESS], {NESS: [{"nome": "Zé", "telefone": "11 98888-7777"}]})
    cli = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"graph_ness": (lambda: graph)}), client=("127.0.0.1", 50000))
    r = cli.post(f"{U}/sincronizar", headers={**BOSS, **JSON}, content="{}")
    assert r.status_code == 200, r.text  # a conta do Gmail cai como "não autorizada" sem derrubar a da ness
    assert r.json()["dados"]["contas"][NESS] == {"lidos": 1} and "erro" in r.json()["dados"]["contas"][GMAIL]


# ---------------- propostas de contatos (fila de aprovação) ----------------
P = "/api/v1/contatos/propostas"


_ORIGEM = {"criar": "whatsapp", "corrigir": "telefone_invalido", "corrigir_nome": "nome_sujo", "apagar_telefone": "telefone_invalido", "apagar_contato": "nome_curto"}


def _proposta(banco, tipo="criar", nome="Joana Silva", tel="+5511912345678", estado="pendente"):
    c = conectar(banco)
    pid = c.execute("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, origem, estado) values (?, 'resper@ness.com.br', ?, ?, ?, ?, ?)",
                    (tipo, None if tipo == "criar" else "g1", nome, tel, _ORIGEM[tipo], estado)).lastrowid
    c.close()
    return pid


def test_propostas_listam_e_so_boss(cli, banco):
    pid = _proposta(banco)
    r = cli.get(P, headers=BOSS)
    assert r.status_code == 200
    item = r.json()["dados"]["itens"][0]
    assert item["id"] == pid and item["nome_depois"] == "Joana Silva" and item["telefone_depois"] == "+5511912345678"
    assert {"tipo", "conta", "nome_antes", "telefone_antes", "origem", "estado", "motivo", "criada_em", "decidida_em", "decidida_por", "aplicada_em"} <= set(item)
    assert cli.get(P, headers=VIP).status_code == 403
    assert _post(cli, f"{P}/{pid}/decisao", {"estado": "aprovada"}, VIP).status_code == 403
    assert _post(cli, f"{P}/aprovar-correcoes", None, VIP).status_code == 403


def test_listar_filtra_por_estado_e_estado_invalido_400(cli, banco):
    _proposta(banco)
    _proposta(banco, nome="Ana", tel="+5511900000001", estado="recusada")
    assert [i["estado"] for i in cli.get(P, headers=BOSS).json()["dados"]["itens"]] == ["pendente"]
    assert [i["estado"] for i in cli.get(P + "?estado=recusada", headers=BOSS).json()["dados"]["itens"]] == ["recusada"]
    r = cli.get(P + "?estado=xis", headers=BOSS)
    assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida"


def test_listar_mostra_estado_do_interruptor(cli, banco):
    assert cli.get(P, headers=BOSS).json()["dados"]["escrita"] == "desligado"
    c = conectar(banco)
    c.execute("insert into parametro(chave, valor) values ('contatos.escrita', '\"ligado\"')")
    c.close()
    assert cli.get(P, headers=BOSS).json()["dados"]["escrita"] == "ligado"


def _audit_quebrado(monkeypatch):
    def _x(*a, **k):
        raise RuntimeError("falha na auditoria")
    monkeypatch.setattr("gabi.rotas.contatos._audit", _x)


def test_falha_na_auditoria_desfaz_a_decisao(banco, monkeypatch):
    pid = _proposta(banco)
    _audit_quebrado(monkeypatch)
    sem_erro_http = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000), raise_server_exceptions=False)
    assert _post(sem_erro_http, f"{P}/{pid}/decisao", {"estado": "aprovada"}).status_code >= 500
    c = conectar(banco)
    assert c.execute("select estado, decidida_por from contato_proposta where id=?", (pid,)).fetchone()[:] == ("pendente", None)
    c.close()


def test_falha_na_auditoria_desfaz_aprovar_correcoes(banco, monkeypatch):
    pid = _proposta(banco, "corrigir", "A", "+5511911111111")
    _audit_quebrado(monkeypatch)
    sem_erro_http = TestClient(criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA), client=("127.0.0.1", 50000), raise_server_exceptions=False)
    assert _post(sem_erro_http, f"{P}/aprovar-correcoes", {"ids": [pid]}).status_code >= 500
    c = conectar(banco)
    assert c.execute("select estado from contato_proposta where id=?", (pid,)).fetchone()[0] == "pendente"
    c.close()


def test_aprovar_correcoes_aprova_adicionar_email_e_lista_email_depois(cli, banco):
    c = conectar(banco)
    pid = c.execute("insert into contato_proposta(tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, email_depois) "
                    "values ('adicionar_email', 'resper@ness.com.br', 'g9', 'Joana', '+5511912345678', 'Joana', '+5511912345678', 'google_email', 'a@x.com;b@x.com')").lastrowid
    c.close()
    item = [i for i in cli.get(P, headers=BOSS).json()["dados"]["itens"] if i["id"] == pid][0]
    assert item["tipo"] == "adicionar_email" and item["email_depois"] == "a@x.com;b@x.com"
    r = _post(cli, f"{P}/aprovar-correcoes", {"ids": [pid]})
    assert r.status_code == 200 and r.json()["dados"] == {"aprovadas": 1}
    assert [i["id"] for i in cli.get(P + "?estado=aprovada", headers=BOSS).json()["dados"]["itens"]] == [pid]


def test_aprovar_correcoes_sem_nenhuma_nao_audita(cli, banco):
    pid = _proposta(banco, "criar")
    assert _post(cli, f"{P}/aprovar-correcoes", {"ids": [pid]}).json()["dados"] == {"aprovadas": 0}
    assert [o for o in _decisoes(banco) if "correç" in o] == []


def test_decisao_aprova_e_audita_sem_dados_pessoais(cli, banco):
    pid = _proposta(banco)
    r = _post(cli, f"{P}/{pid}/decisao", {"estado": "aprovada"})
    assert r.status_code == 200 and r.json()["dados"] == {"id": pid, "estado": "aprovada"}
    c = conectar(banco)
    linha = c.execute("select estado, decidida_por from contato_proposta where id=?", (pid,)).fetchone()
    assert (linha["estado"], linha["decidida_por"]) == ("aprovada", "boss@x.com")
    audit = [o for o in _decisoes(banco) if "contato proposta" in o]
    assert audit == [f"contatos: contato proposta {pid} → aprovada"]
    assert "Joana" not in audit[0] and "5511912345678" not in audit[0]


def test_decisao_em_proposta_ja_decidida_409(cli, banco):
    pid = _proposta(banco)
    assert _post(cli, f"{P}/{pid}/decisao", {"estado": "recusada"}).status_code == 200
    r = _post(cli, f"{P}/{pid}/decisao", {"estado": "aprovada"})
    assert r.status_code == 409 and r.json()["erro"] == "conflito"


def test_decisao_estado_invalido_400_e_inexistente_404(cli, banco):
    pid = _proposta(banco)
    for corpo in ({"estado": "aplicada"}, {"estado": 3}, {}):
        r = _post(cli, f"{P}/{pid}/decisao", corpo)
        assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida"
    r = _post(cli, f"{P}/9999/decisao", {"estado": "aprovada"})
    assert r.status_code == 404 and r.json()["erro"] == "nao_encontrado"


def test_aprovar_correcoes_so_dos_ids_enviados(cli, banco):
    a = _proposta(banco, "corrigir", "A", "+5511911111111")
    b = _proposta(banco, "corrigir", "B", "+5511922222222")
    fora = _proposta(banco, "corrigir", "D", "+5511944444444")
    criar = _proposta(banco, "criar", "C", "+5511933333333")
    ja = _proposta(banco, "corrigir", "E", "+5511955555555", estado="recusada")
    r = _post(cli, f"{P}/aprovar-correcoes", {"ids": [a, b, criar, ja, 99999]})
    assert r.status_code == 200 and r.json()["dados"] == {"aprovadas": 2}
    assert [i["id"] for i in cli.get(P, headers=BOSS).json()["dados"]["itens"]] == [fora, criar]
    assert [i["id"] for i in cli.get(P + "?estado=recusada", headers=BOSS).json()["dados"]["itens"]] == [ja]
    audit = [o for o in _decisoes(banco) if "correç" in o]
    assert audit == ["contatos: aprovou 2 correção(ões) de contato"]


def test_aprovar_correcoes_inclui_corrigir_nome_e_nunca_apagar(cli, banco):
    nome = _proposta(banco, "corrigir_nome", "Ana", "")
    apagar_tel = _proposta(banco, "apagar_telefone", "Bia", "")
    apagar_contato = _proposta(banco, "apagar_contato", "U", "")
    r = _post(cli, f"{P}/aprovar-correcoes", {"ids": [nome, apagar_tel, apagar_contato]})
    assert r.status_code == 200 and r.json()["dados"] == {"aprovadas": 1}
    pendentes = [i["id"] for i in cli.get(P, headers=BOSS).json()["dados"]["itens"]]
    assert pendentes == [apagar_tel, apagar_contato]
    assert [i["id"] for i in cli.get(P + "?estado=aprovada", headers=BOSS).json()["dados"]["itens"]] == [nome]


def test_listar_devolve_os_tipos_novos(cli, banco):
    ids = [_proposta(banco, t, "X", "") for t in ("corrigir_nome", "apagar_telefone", "apagar_contato")]
    itens = cli.get(P, headers=BOSS).json()["dados"]["itens"]
    assert [(i["id"], i["tipo"]) for i in itens] == list(zip(ids, ("corrigir_nome", "apagar_telefone", "apagar_contato")))


@pytest.mark.parametrize("corpo", [{}, {"ids": []}, {"ids": None}, {"ids": "1"}, {"ids": [1, "2"]}, {"ids": [True]}, {"ids": [1.5]}])
def test_aprovar_correcoes_sem_ids_validos_400(cli, banco, corpo):
    pid = _proposta(banco, "corrigir", "A", "+5511911111111")
    r = _post(cli, f"{P}/aprovar-correcoes", corpo)
    assert r.status_code == 400 and r.json()["erro"] == "requisicao_invalida"
    c = conectar(banco)
    assert c.execute("select estado from contato_proposta where id=?", (pid,)).fetchone()[0] == "pendente"
    c.close()


def test_recusar_proposta_ja_aprovada_e_auditada(cli, banco):
    pid = _proposta(banco)
    assert _post(cli, f"{P}/{pid}/decisao", {"estado": "aprovada"}).status_code == 200
    r = _post(cli, f"{P}/{pid}/decisao", {"estado": "recusada"})
    assert r.status_code == 200 and r.json()["dados"] == {"id": pid, "estado": "recusada"}
    assert [o for o in _decisoes(banco) if "contato proposta" in o] == [f"contatos: contato proposta {pid} → aprovada", f"contatos: contato proposta {pid} → recusada"]
    assert [i["id"] for i in cli.get(P + "?estado=recusada", headers=BOSS).json()["dados"]["itens"]] == [pid]


@pytest.mark.parametrize("estado", ["aplicada", "falhou"])
def test_aplicada_ou_falhou_nao_volta_409(cli, banco, estado):
    pid = _proposta(banco, estado=estado)
    for e in ("aprovada", "recusada"):
        r = _post(cli, f"{P}/{pid}/decisao", {"estado": e})
        assert r.status_code == 409 and r.json()["erro"] == "conflito"


def test_aprovada_nao_aprova_de_novo_409(cli, banco):
    pid = _proposta(banco, estado="aprovada")
    assert _post(cli, f"{P}/{pid}/decisao", {"estado": "aprovada"}).status_code == 409
