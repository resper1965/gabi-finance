import time

from gabi.db import conectar

from tests.rotas.test_dinheiro_api import AGORA, BOSS, VIP, banco, cli, get, post  # noqa: F401  (fixtures)


def _semear(banco, n_emails=3):
    c = conectar(banco)
    c.execute("insert into email_fonte(id, conta, provedor, estado) values (1,'a@ness.com','google','sim')")
    for i in range(n_emails):
        c.execute("insert into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, classe, prioridade, motivo, estado, atualizado_em) "
                  "values (1,?,?,'x@y.com','Contrato',?, ?, 2, 'cliente', 'classificada', ?)",
                  (f"m{i}", f"m{i}t", "2026-10-08T10:00:00Z", "emergencial" if i == 0 else "importante", "2026-10-08T10:00:00Z"))
    c.execute("insert into agenda_fonte(id, conta, provedor, estado) values (1,'a@ness.com','google','sim')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (1,'e1','2026-10-08T17:00:00+00:00','2026-10-08T18:00:00+00:00','2026-10-08','2026-10-08','Reunião A')")
    c.execute("insert into agenda_evento(fonte_id, externo_id, inicio_utc, fim_utc, dia_local, dia_fim_local, titulo) values (1,'e2','2026-10-08T17:30:00+00:00','2026-10-08T18:30:00+00:00','2026-10-08','2026-10-08','Reunião B')")
    c.close()


def test_rotas_do_dia_exigem_boss(cli):
    for url in ("/api/v1/hoje", "/api/v1/agenda"):
        assert get(cli, url, VIP).status_code == 403 and cli.get(url).status_code == 401, url


def test_hoje_traz_prioridades_agenda_correio_e_dinheiro(cli, banco):
    _semear(banco)
    j = get(cli, "/api/v1/hoje").json()
    assert {"dados_ate", "dados"} <= set(j)
    d = j["dados"]
    assert set(d) == {"prioridades", "agenda", "correio_importantes", "dinheiro"}
    assert len(d["correio_importantes"]) == 3 and len(d["agenda"]) == 2 and d["dinheiro"]["atrasadas"]["n"] == 1
    assert {p["tipo"] for p in d["prioridades"]} == {"email_emergencial", "conflito"}


def test_hoje_carrega_em_menos_de_1s_com_muitos_emails(cli, banco):
    _semear(banco, n_emails=3000)
    t = time.perf_counter()
    assert get(cli, "/api/v1/hoje").status_code == 200
    assert time.perf_counter() - t < 1.0


def test_hoje_le_so_de_tabelas_prontas():
    import inspect
    from gabi import dia
    fonte = inspect.getsource(dia)
    assert "fontes." not in fonte and "urllib" not in fonte and "httpx" not in fonte


def test_rota_agenda_novo_formato(cli, banco):
    _semear(banco)
    d = get(cli, "/api/v1/agenda?de=2026-10-08&ate=2026-10-08").json()["dados"]
    assert [e["titulo"] for e in d["eventos"]] == ["Reunião A", "Reunião B"]
    e = d["eventos"][0]
    assert e["inicio_local"] == "2026-10-08T14:00:00-03:00" and e["dia_inteiro"] is False and e["fonte"] == "a@ness.com"
    assert e["inicio"] == e["inicio_local"] and e["fim"] == e["fim_local"]  # alias até o painel migrar
    assert len(d["conflitos"]) == 1 and d["conflitos"][0]["sugestao_inicio"] == "2026-10-08T15:30:00-03:00"
