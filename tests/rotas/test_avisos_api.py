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
AGORA = dt.datetime(2026, 10, 16, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


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


def _aviso(banco, tipo, payload, quando="2026-10-16T10:00:00+00:00", entregue=None):
    c = conectar(banco)
    i = c.execute("insert into aviso(tipo, payload, criado_em, entregue_em) values (?,?,?,?)", (tipo, json.dumps(payload), quando, entregue)).lastrowid
    c.close()
    return i


def test_lista_so_avisos_abertos_do_boss_com_titulo_e_texto_em_pt_br(cli, banco):
    velho = _aviso(banco, "conta_atrasada", {"chave": "a", "nome": "Cristina Yabe", "vencimento": "2026-10-07", "valor": "370.00"}, quando="2026-10-15T10:00:00+00:00")
    novo = _aviso(banco, "rodada_parada", {"chave": "x", "motivo": "as 2 últimas rodadas de extratos não foram conferidas"})
    _aviso(banco, "vence_hoje", {"chave": "h", "itens": []}, entregue="2026-10-16T10:30:00+00:00")   # já lido: não aparece
    r = cli.get("/api/v1/avisos", headers=BOSS)
    assert r.status_code == 200
    itens = r.json()["dados"]["itens"]
    assert [i["id"] for i in itens] == [novo, velho]                                         # mais novo primeiro
    assert itens[0]["titulo"] == "Dados do banco parados" and "não foram conferidas" in itens[0]["texto"]
    assert itens[1]["titulo"] == "Conta atrasada: Cristina Yabe" and "R$ 370.00" in itens[1]["texto"] and "2026-10-07" in itens[1]["texto"]
    assert cli.get("/api/v1/avisos", headers=VIP).status_code == 403 and cli.get("/api/v1/avisos").status_code == 401


def test_marcar_lido_registra_entregue_em_e_e_idempotente(cli, banco):
    aid = _aviso(banco, "servico_falhou", {"chave": "u", "unidade": "gabi-brain-saldos.service"})
    r1 = cli.post(f"/api/v1/avisos/{aid}/lido", headers={**BOSS, "Content-Type": "application/json"}, content="{}")
    assert r1.status_code == 200
    c = conectar(banco)
    primeiro = c.execute("select entregue_em from aviso where id=?", (aid,)).fetchone()[0]
    assert primeiro is not None and c.execute("select count(*) from decisao where o_que like ?", (f"%aviso {aid}%",)).fetchone()[0] == 1
    r2 = cli.post(f"/api/v1/avisos/{aid}/lido", headers={**BOSS, "Content-Type": "application/json"}, content="{}")
    assert r2.status_code == 200 and c.execute("select entregue_em from aviso where id=?", (aid,)).fetchone()[0] == primeiro
    assert c.execute("select count(*) from decisao where o_que like ?", (f"%aviso {aid}%",)).fetchone()[0] == 1
    assert cli.post("/api/v1/avisos/9999/lido", headers={**BOSS, "Content-Type": "application/json"}, content="{}").status_code == 404
    assert cli.get("/api/v1/avisos", headers=BOSS).json()["dados"]["itens"] == []


def test_so_o_boss_marca_como_lido(cli, banco):
    aid = _aviso(banco, "vence_hoje", {"chave": "h", "itens": []})
    assert cli.post(f"/api/v1/avisos/{aid}/lido", headers={**VIP, "Content-Type": "application/json"}, content="{}").status_code == 403


def test_contagens_inclui_os_avisos_abertos_no_sino(cli, banco):
    antes = cli.get("/api/v1/contagens", headers=BOSS).json()["dados"]
    _aviso(banco, "rodada_parada", {"chave": "a", "motivo": "x"}); _aviso(banco, "servico_falhou", {"chave": "b", "unidade": "u"})
    _aviso(banco, "vence_hoje", {"chave": "c", "itens": []}, entregue="2026-10-16T10:30:00+00:00")
    depois = cli.get("/api/v1/contagens", headers=BOSS).json()["dados"]
    assert depois["menu"]["avisos"] == 2 and depois["sino"] == antes["sino"] + 2


def test_descrever_aviso_de_caixa_para_reconectar():
    from gabi.rotas.avisos import descrever
    titulo, texto = descrever("caixa_reconectar", {"endereco": "a@ionic.health"})
    assert "a@ionic.health" in titulo and "credencial" in texto


def test_descrever_aviso_de_agenda_para_reconectar():
    from gabi.rotas.avisos import descrever
    titulo, texto = descrever("agenda_reconectar", {"chave": "a@x.com", "conta": "a@x.com"})
    assert "a@x.com" in titulo and "agenda" in texto


def test_descrever_avisos_do_correio():
    from gabi.rotas.avisos import descrever
    titulo, texto = descrever("email_emergencial", {"chave": "T1", "remetente": "banco@x.com", "assunto": "Boleto vence hoje", "motivo": "prazo hoje"})
    assert "banco@x.com" in titulo and "Boleto vence hoje" in titulo and "prazo hoje" in texto
    titulo, texto = descrever("email_lixeira_resumo", {"chave": "2026-10-12", "total": 12, "itens": [{"remetente": "promo@loja.com", "assunto": "Oferta"}]})
    assert "12" in titulo and "promo@loja.com" in texto and "Oferta" in texto and "restaur" in texto.lower()
    assert "modelo" in descrever("email_sem_modelo", {"chave": "modelo", "motivo": "teto de custo do modelo"})[0].lower()
    assert "teto de custo do modelo" in descrever("email_sem_modelo", {"chave": "modelo", "motivo": "teto de custo do modelo"})[1]
    titulo, texto = descrever("email_reconectar", {"chave": "a@x.com", "conta": "a@x.com"})
    assert "a@x.com" in titulo and "credencial" in texto
