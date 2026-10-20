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


def test_so_boss_acessa(cli):
    for url in ("/api/v1/escuta/remetentes", "/api/v1/escuta/grupos", "/api/v1/escuta/parametros"):
        assert cli.get(url, headers=VIP).status_code == 403
        assert cli.get(url).status_code == 401
        assert cli.get(url, headers=BOSS).status_code == 200
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "familia"}, VIP).status_code == 403
    assert cli.post(f"/api/v1/escuta/remetentes/{NQ}/ignorar", content="{}", headers=JSON).status_code == 401
    assert _put(cli, {"modo": "ativo"}, VIP).status_code == 403


def test_aprovar_sem_papel_ou_papel_invalido_400(cli, banco):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {}).status_code == 400
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "chefe"}).status_code == 400
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "familia", "nome": 3}).status_code == 400


def test_numero_que_nao_normaliza_404_ou_400(cli):
    assert _post(cli, "/api/v1/escuta/remetentes/123/aprovar", {"papel": "familia"}).status_code in (400, 404)
    assert _post(cli, "/api/v1/escuta/remetentes/abc/ignorar").status_code in (400, 404)


def test_aprovar_move_da_fila_para_aprovados(cli, banco):
    _pendente(banco)
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert [f["numero"] for f in d["fila"]] == [N] and d["aprovados"] == []
    r = _post(cli, f"/api/v1/escuta/remetentes/{NQ}/aprovar", {"papel": "prestador", "nome": "Joana Silva"})
    assert r.status_code == 200
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert d["fila"] == []
    assert len(d["aprovados"]) == 1
    a = d["aprovados"][0]
    assert a["numero"] == N and a["papel"] == "prestador" and a["nome"] == "Joana Silva" and a["pessoa_id"]
    assert sum("aprovou" in o for o in _decisoes(banco)) == 1  # auditado uma vez só


@pytest.mark.parametrize("seg", ["%2B5511912345678", "5511912345678", "+5511912345678", "11912345678", "%2B55%2011%2091234-5678"])
def test_numero_em_formatos_diferentes_e_o_mesmo_remetente(cli, banco, seg):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{seg}/aprovar", {"papel": "familia"}).status_code == 200
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert [a["numero"] for a in d["aprovados"]] == [N]
    c = conectar(banco)
    assert c.execute("select count(*) from escuta_remetente").fetchone()[0] == 1
    c.close()


@pytest.mark.parametrize("acao,estado", [("ignorar", "ignorado"), ("bloquear", "bloqueado")])
def test_ignorar_e_bloquear(cli, banco, acao, estado):
    _pendente(banco)
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/{acao}").status_code == 200
    c = conectar(banco)
    assert c.execute("select estado from escuta_remetente where numero=?", (N,)).fetchone()[0] == estado
    c.close()
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert d["fila"] == [] and d["aprovados"] == []
    assert any(estado in o for o in _decisoes(banco))


def test_ignorar_nao_toca_no_spool(cli, banco, tmp_path):
    spool = tmp_path / "spool"
    (spool / "anexos").mkdir(parents=True)
    anexo = spool / "anexos" / "a.pdf"
    anexo.write_bytes(b"x")
    _pendente(banco)
    c = conectar(banco)
    c.execute("insert into escuta_msg(id_externo, de, grupo, recebida_em, anexo_caminho) values ('1',?,0,'2026-10-16T10:00:00+00:00',?)", (N, str(anexo)))
    c.close()
    antes = sorted(p.name for p in spool.rglob("*"))
    assert _post(cli, f"/api/v1/escuta/remetentes/{NQ}/ignorar").status_code == 200
    assert anexo.exists() and sorted(p.name for p in spool.rglob("*")) == antes
    c = conectar(banco)
    assert c.execute("select anexo_caminho from escuta_msg").fetchone()[0] is None
    c.close()


def test_grupos_listar_e_aprovar_404(cli, banco):
    c = conectar(banco)
    c.execute("insert into escuta_grupo(id_grupo, nome) values ('g1@g.us','Escola')")
    c.close()
    g = cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"]
    assert g == [{"id_grupo": "g1@g.us", "nome": "Escola", "aprovado": False, "comprovantes": False}]
    assert _post(cli, "/api/v1/escuta/grupos/g1@g.us/aprovar").status_code == 200
    assert cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"][0]["aprovado"] is True
    assert any("g1@g.us" in o for o in _decisoes(banco))
    assert _post(cli, "/api/v1/escuta/grupos/nao-existe/aprovar").status_code == 404


def test_parametros_padrao_quando_nao_definidos(cli):
    p = cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]
    assert p["modo"] == "registro" and p["palavras_risco"] == [] and p["horas_sem_receber"] == 12 and p["anexo_max_mb"] == 25


def test_parametros_validam_modo(cli):
    assert _put(cli, {"modo": "outro"}).status_code == 400
    assert _put(cli, {"modo": 1}).status_code == 400
    assert _put(cli, {"modo": "ativo"}).status_code == 200
    assert cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]["modo"] == "ativo"


@pytest.mark.parametrize("corpo", [
    {"palavras_risco": "x"}, {"palavras_risco": [""]}, {"palavras_risco": ["a", 3]}, {"palavras_risco": ["x" * 61]},
    {"palavras_risco": ["a"] * 201}, {"palavras_risco": ["  "]},
    {"horas_sem_receber": 0}, {"horas_sem_receber": 169}, {"horas_sem_receber": 1.5}, {"horas_sem_receber": True}, {"horas_sem_receber": "3"},
    {"anexo_max_mb": 0}, {"anexo_max_mb": 101}, {"anexo_max_mb": None},
    {"desconhecido": 1}, {},
])
def test_parametros_invalidos_400(cli, corpo):
    assert _put(cli, corpo).status_code == 400


def test_parametros_validos_e_auditoria_sem_palavras(cli, banco):
    r = _put(cli, {"palavras_risco": ["me matar", "sumir"], "horas_sem_receber": 24, "anexo_max_mb": 10, "modo": "ativo"})
    assert r.status_code == 200
    p = cli.get("/api/v1/escuta/parametros", headers=BOSS).json()["dados"]
    assert p == {"modo": "ativo", "palavras_risco": ["me matar", "sumir"], "horas_sem_receber": 24, "anexo_max_mb": 10}
    c = conectar(banco)
    assert json.loads(c.execute("select valor from parametro where chave='escuta.horas_sem_receber'").fetchone()[0]) == 24
    assert _put(cli, {"horas_sem_receber": 1, "anexo_max_mb": 100}).status_code == 200
    linhas = c.execute("select quem, o_que, origem from decisao where origem='escuta'").fetchall()
    c.close()
    assert len(linhas) == 2 and all(x["quem"] == "boss@x.com" for x in linhas)
    todo = " ".join(x["o_que"] for x in linhas)
    assert "palavras_risco" in todo and "me matar" not in todo and "sumir" not in todo


# ---------------- contatos do Google ----------------
from gabi.fontes.google_contatos import ErroGoogleContatos  # noqa: E402

GMAIL, NESS = "resper@gmail.com", "resper@ness.com.br"
U = "/api/v1/escuta/contatos"


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
    assert "text/csv" in spec["paths"]["/api/v1/escuta/contatos/so-na-ness.csv"]["get"]["responses"]["200"]["content"]


LIDQ = "123456789012345%40lid"
LID = "123456789012345@lid"


def test_i4_id_cru_aparece_na_fila_e_aceita_ignorar_bloquear_aprovar(cli, banco):
    _pendente(banco, numero=LID, nome=None)
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert [f["numero"] for f in d["fila"]] == [LID]
    assert _post(cli, f"/api/v1/escuta/remetentes/{LIDQ}/aprovar", {"papel": "familia"}).status_code == 400   # id cru exige nome
    r = _post(cli, f"/api/v1/escuta/remetentes/{LIDQ}/aprovar", {"papel": "familia", "nome": "Tia"})
    assert r.status_code == 200 and r.json()["dados"]["numero"] == LID
    d = cli.get("/api/v1/escuta/remetentes", headers=BOSS).json()["dados"]
    assert d["fila"] == [] and [a["numero"] for a in d["aprovados"]] == [LID]
    assert _post(cli, f"/api/v1/escuta/remetentes/{LIDQ}/bloquear").status_code == 200
    c = conectar(banco)
    assert c.execute("select estado from escuta_remetente where numero=?", (LID,)).fetchone()[0] == "bloqueado"
    c.close()


def test_i4_id_cru_desconhecido_continua_404(cli):
    assert _post(cli, f"/api/v1/escuta/remetentes/{LIDQ}/ignorar").status_code == 404


def test_i5_grupo_visto_no_spool_aparece_aprova_e_e_classificado(cli, banco, tmp_path):
    from gabi.dinheiro.modelo import Orcamento
    from gabi.escuta.caixa import ingerir_spool
    from gabi.escuta.processar import processar
    spool = tmp_path / "spool"
    spool.mkdir()
    msg = {"id_externo": "g1", "de": "5511900000001@s.whatsapp.net", "grupo": True, "id_grupo": "999@g.us",
           "recebida_em": "2026-10-16T09:00:00", "texto": "oi grupo"}
    (spool / "g1.json").write_text(json.dumps(msg))
    c = conectar(banco)
    ingerir_spool(c, spool, "2026-10-16T12:00:00+00:00")
    assert cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"] == [{"id_grupo": "999@g.us", "nome": None, "aprovado": False, "comprovantes": False}]
    assert _post(cli, "/api/v1/escuta/grupos/999@g.us/aprovar").status_code == 200

    class M:
        n = 0

        def completar(self, prompt, *, forte):
            M.n += 1
            return json.dumps({"tipo": "nada", "confianca": 0.9, "campos": {}}), 0.001

    class D:
        def documento(self, *a): ...
    r = processar(c, D(), M(), Orcamento(1.0, 10.0), "2026-10-16T12:00:00+00:00", "registro")
    assert M.n == 1 and r["classificadas"] == 1
    assert c.execute("select estado, tipo from escuta_msg").fetchone()[:] == ("processada", "nada")
    c.close()


def test_i3_descrever_escuta_sem_permissao_so_numero_e_nome():
    from gabi.rotas.avisos import descrever
    t, x = descrever("escuta_sem_permissao", {"numero": N, "nome": "Joana"})
    assert "Pedido de Joana sem permissão" in t and "Cadastros" in (t + x)


def test_i6_m5_descrever_escuta_falhou_e_sem_modelo_neutro():
    from gabi.rotas.avisos import descrever
    t, x = descrever("escuta_falhou", {"numero": N, "nome": "Joana"})
    assert "Joana" in t and "abra a conversa" in (t + x)
    t, x = descrever("escuta_sem_modelo", {"motivo": "teto de custo do modelo"})
    assert x == "a escuta está sem modelo disponível agora: teto de custo do modelo" and "não está configurado" not in x


def test_i7_descrever_escuta_anexo_grande():
    from gabi.rotas.avisos import descrever
    t, x = descrever("escuta_anexo_grande", {"numero": N, "nome": "Joana"})
    assert "Joana" in t and "25" not in t and "grande" in (t + x).lower() and x != "{}"


def test_grupo_caixa_de_comprovantes_so_um_e_exige_aprovado(cli, banco):
    c = conectar(banco)
    c.execute("insert into escuta_grupo(id_grupo, nome, aprovado) values ('a@g.us','A',1), ('b@g.us','B',1), ('c@g.us','C',0)")
    c.close()
    assert _post(cli, "/api/v1/escuta/grupos/nao-existe/comprovantes").status_code == 404
    assert _post(cli, "/api/v1/escuta/grupos/c@g.us/comprovantes").status_code == 409  # não aprovado
    assert _post(cli, "/api/v1/escuta/grupos/a@g.us/comprovantes").status_code == 200
    assert _post(cli, "/api/v1/escuta/grupos/b@g.us/comprovantes").status_code == 200  # troca a caixa
    g = {x["id_grupo"]: x["comprovantes"] for x in cli.get("/api/v1/escuta/grupos", headers=BOSS).json()["dados"]["grupos"]}
    assert g == {"a@g.us": False, "b@g.us": True, "c@g.us": False}
    c = conectar(banco)
    assert c.execute("select count(*) from decisao where o_que like 'escuta: caixa de comprovantes%'").fetchone()[0] == 2
    c.close()


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
P = "/api/v1/escuta/contatos/propostas"


def _proposta(banco, tipo="criar", nome="Joana Silva", tel="+5511912345678", estado="pendente"):
    c = conectar(banco)
    pid = c.execute("insert into contato_proposta(tipo, conta, graph_id, nome_depois, telefone_depois, origem, estado) values (?, 'resper@ness.com.br', ?, ?, ?, ?, ?)",
                    (tipo, "g1" if tipo == "corrigir" else None, nome, tel, "telefone_invalido" if tipo == "corrigir" else "whatsapp", estado)).lastrowid
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
    monkeypatch.setattr("gabi.rotas.escuta._audit", _x)


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
    assert audit == [f"escuta: contato proposta {pid} → aprovada"]
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
    assert audit == ["escuta: aprovou 2 correção(ões) de contato"]


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
    assert [o for o in _decisoes(banco) if "contato proposta" in o] == [f"escuta: contato proposta {pid} → aprovada", f"escuta: contato proposta {pid} → recusada"]
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
