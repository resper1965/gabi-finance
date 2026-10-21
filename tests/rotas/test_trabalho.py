import json
import time

from gabi.db import conectar
from gabi.trabalho import email

from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, cli, get, post  # noqa: F401  (fixtures)


def _semear(banco, n_emails=3):
    c = conectar(banco)
    c.execute("insert into caixa_email(id, endereco, provedor, empresa_id, estado) values (1,'a@ness.com','google','e1','sim')")
    c.execute("insert into caixa_email(id, endereco, provedor, estado) values (2,'b@x.com','graph','sim')")
    c.execute("insert into parametro(chave, valor) values ('email_palavras_relevantes', ?)", (json.dumps(["contrato"]),))
    msgs = [dict(message_id=f"<m{i}>", remetente="x@y.com", assunto="Contrato novo" if i % 2 == 0 else "Oi", recebido_em=f"2026-10-08T{10 + i % 10:02d}:00:00Z", corpo="t")
            for i in range(n_emails)]
    email.ingerir_email(c, 1, lambda cx, cur: (msgs, None))
    email.ingerir_email(c, 2, lambda cx, cur: ([dict(message_id="<b1>", remetente="z@z.com", assunto="Contrato B", recebido_em="2026-10-08T09:00:00Z", corpo="")], None))
    c.execute("insert into agenda_fonte(id, conta, provedor, estado) values (1,'a@ness.com','google','sim')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (1,'e1','2026-10-08T17:00:00+00:00','2026-10-08T18:00:00+00:00','2026-10-08','2026-10-08','Reunião A')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (1,'e2','2026-10-08T17:30:00+00:00','2026-10-08T18:30:00+00:00','2026-10-08','2026-10-08','Reunião B')")
    c.execute("insert into tarefa(origem, externo_id, titulo) values ('graph','t1','Enviar proposta')")
    c.close()


def test_rotas_de_trabalho_exigem_boss(cli):
    for url in ("/api/v1/hoje", "/api/v1/frentes", "/api/v1/agenda", "/api/v1/mensagens", "/api/v1/tarefas"):
        assert get(cli, url, VIP).status_code == 403 and cli.get(url).status_code == 401, url


def test_hoje_traz_as_quatro_partes_com_envelope(cli, banco):
    _semear(banco)
    j = get(cli, "/api/v1/hoje").json()
    assert {"dados_ate", "dados"} <= set(j)
    d = j["dados"]
    assert d["emails_importantes"] and len(d["agenda"]) == 2 and d["dinheiro"]["atrasadas"]["n"] == 1
    assert any(p["tipo"] == "conflito" for p in d["prioridades"])


def test_filtro_recorta_a_tela_inteira(cli, banco):
    _semear(banco)
    d = get(cli, "/api/v1/hoje?filtro=e1").json()["dados"]      # só a caixa da empresa e1
    assert {m["caixa"] for m in d["emails_importantes"]} == {"a@ness.com"}
    assert d["dinheiro"] is None
    assert get(cli, "/api/v1/hoje?filtro=e9").json()["dados"]["emails_importantes"] == []


def test_filtro_invalido_da_400(cli):
    assert get(cli, "/api/v1/hoje?filtro=a'b").status_code == 400


def test_hoje_carrega_em_menos_de_1s_com_muitos_itens(cli, banco):
    _semear(banco, n_emails=3000)
    t = time.perf_counter()
    assert get(cli, "/api/v1/hoje").status_code == 200
    assert time.perf_counter() - t < 1.0


def test_hoje_le_so_de_tabelas_prontas():
    import inspect
    from gabi.trabalho import hoje
    fonte = inspect.getsource(hoje)
    assert "fontes." not in fonte and "urllib" not in fonte and "httpx" not in fonte


def test_frente_criar_sugerir_confirmar(cli, banco):
    _semear(banco)
    fid = post(cli, "/api/v1/frentes", {"nome": "Acme", "tipo": "cliente", "regra": {"palavras": ["contrato"]}}).json()["dados"]["id"]
    assert post(cli, "/api/v1/frentes", {"nome": "X", "tipo": "invalido"}).status_code == 400
    assert get(cli, f"/api/v1/frentes/{fid}").json()["dados"]["emails"] == []
    assert post(cli, f"/api/v1/frentes/{fid}/itens/1/confirmar").status_code == 200
    assert len(get(cli, f"/api/v1/frentes/{fid}").json()["dados"]["emails"]) == 1
    assert get(cli, "/api/v1/frentes/999").status_code == 404


def test_concluir_tarefa_chama_a_origem(banco):
    from fastapi.testclient import TestClient
    from gabi.api import criar_app
    _semear(banco)
    chamadas = []
    app = criar_app(banco, permite_tcp_local=True, relogio=lambda: AGORA, fontes={"concluir_tarefa": lambda: (lambda o, e: chamadas.append((o, e)))})
    c = TestClient(app, client=("127.0.0.1", 50000))
    assert post(c, "/api/v1/tarefas/1/concluir").status_code == 200
    assert chamadas == [("graph", "t1")]
    assert get(c, "/api/v1/tarefas").json()["dados"]["itens"][0]["estado"] == "concluida"


def test_concluir_sem_rede_registra_o_pedido_e_nao_marca_ate_o_job_agir(cli, banco):
    _semear(banco)
    r = post(cli, "/api/v1/tarefas/1/concluir")
    assert r.status_code == 200 and r.json()["dados"]["pendente"] is True
    assert get(cli, "/api/v1/tarefas").json()["dados"]["itens"][0]["estado"] == "aberta"
    c = conectar(banco)
    assert c.execute("select pedido_concluir_em from tarefa where id=1").fetchone()[0] is not None


def test_caixas_de_email_cadastro_nasce_a_decidir_e_so_boss(cli):
    assert post(cli, "/api/v1/caixas-email", {"endereco": "x@y.com", "provedor": "google"}, VIP).status_code == 403
    assert post(cli, "/api/v1/caixas-email", {"endereco": "x@y.com", "provedor": "google"}).status_code == 201
    item = get(cli, "/api/v1/caixas-email").json()["dados"]["itens"][0]
    assert item["estado"] == "a_decidir" and item["itens"] == 0


def test_caixas_validacao(cli):
    assert post(cli, "/api/v1/caixas-email", {"endereco": "", "provedor": "google"}).status_code == 400
    assert post(cli, "/api/v1/caixas-email", {"endereco": "a@b", "provedor": "imap"}).status_code == 400
    assert post(cli, "/api/v1/caixas-email", {"endereco": "a@b", "provedor": "google", "senha": "x"}).status_code == 400   # nunca guarda segredo
    post(cli, "/api/v1/caixas-email", {"endereco": "a@b", "provedor": "google"})
    assert post(cli, "/api/v1/caixas-email", {"endereco": "a@b", "provedor": "graph"}).status_code == 409


def test_liberar_caixa_pelo_patch(cli):
    cid = post(cli, "/api/v1/caixas-email", {"endereco": "a@b", "provedor": "graph"}).json()["dados"]["id"]
    r = cli.patch(f"/api/v1/caixas-email/{cid}", headers={**BOSS, "Content-Type": "application/json"}, content=json.dumps({"estado": "sim", "ler_a_partir_de": "2026-10-01T00:00:00Z"}))
    assert r.status_code == 200
    assert get(cli, "/api/v1/caixas-email").json()["dados"]["itens"][0]["estado"] == "sim"


def test_entregas_da_linear_so_leitura_e_so_boss(cli, banco):
    c = conectar(banco)
    c.execute("insert into entrega(externo_id, identificador, titulo, prazo, estado) values ('a','ION-1','B','2026-11-01','Todo'), ('b','ION-2','A','2026-10-15','Todo'), ('c','ION-3','S',null,'Todo')")
    c.close()
    assert [i["identificador"] for i in get(cli, "/api/v1/entregas").json()["dados"]["itens"]] == ["ION-2", "ION-1", "ION-3"]
    assert get(cli, "/api/v1/entregas", VIP).status_code == 403
    assert post(cli, "/api/v1/entregas", {}).status_code == 405


def test_rota_agenda_novo_formato(cli, banco):
    _semear(banco)
    d = get(cli, "/api/v1/agenda?de=2026-10-08&ate=2026-10-08").json()["dados"]
    assert [e["titulo"] for e in d["eventos"]] == ["Reunião A", "Reunião B"]
    e = d["eventos"][0]
    assert e["inicio_local"] == "2026-10-08T14:00:00-03:00" and e["dia_inteiro"] is False and e["fonte"] == "a@ness.com"
    assert e["inicio"] == e["inicio_local"] and e["fim"] == e["fim_local"]  # alias até o painel migrar (Task 8)
    assert len(d["conflitos"]) == 1 and d["conflitos"][0]["sugestao_inicio"] == "2026-10-08T15:30:00-03:00"


