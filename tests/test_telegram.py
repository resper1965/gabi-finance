import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.telegram import enviar_avisos

MIGRACOES = Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 10, 15, 0, tzinfo=dt.timezone.utc)
ENV = {"TELEGRAM_BOT_TOKEN": "123:segredo", "TELEGRAM_CHAT_ID": "42"}


class Http:
    def __init__(self, status=200):
        self.status, self.chamadas = status, []

    def __call__(self, url, corpo):
        self.chamadas.append((url, corpo))
        return self.status


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _aviso(con, tipo="conta_atrasada", payload=None, quando=AGORA, lido=False):
    return con.execute("insert into aviso(tipo, payload, criado_em, entregue_em) values (?,?,?,?)",
                       (tipo, json.dumps(payload or {"chave": "k", "nome": "IPTU", "vencimento": "2026-10-01", "valor": "R$ 500,00"}), quando.isoformat(),
                        AGORA.isoformat() if lido else None)).lastrowid


def test_desligado_sem_token_ou_chat_nao_envia_nada(con):
    _aviso(con)
    h = Http()
    assert enviar_avisos(con, {}, AGORA, h) == 0 and enviar_avisos(con, {"TELEGRAM_BOT_TOKEN": "x"}, AGORA, h) == 0
    assert h.chamadas == [] and con.execute("select telegram_em from aviso").fetchone()[0] is None


def test_envia_o_aviso_em_portugues_e_marca_como_enviado(con):
    _aviso(con)
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 1
    url, corpo = h.chamadas[0]
    assert url == "https://api.telegram.org/bot123:segredo/sendMessage" and corpo["chat_id"] == "42"
    assert "IPTU" in corpo["text"] and "Conta atrasada" in corpo["text"]
    assert con.execute("select telegram_em from aviso").fetchone()[0] == AGORA.isoformat()


def test_nao_reenvia_e_so_marca_apos_resposta_200(con):
    _aviso(con)
    assert enviar_avisos(con, ENV, AGORA, Http(500)) == 0
    assert con.execute("select telegram_em from aviso").fetchone()[0] is None  # tenta de novo na próxima rodada
    h = Http()
    enviar_avisos(con, ENV, AGORA, h)
    enviar_avisos(con, ENV, AGORA, h)
    assert len(h.chamadas) == 1


def test_ignora_aviso_lido_e_aviso_velho_para_nao_inundar_ao_ligar(con):
    _aviso(con, lido=True)
    _aviso(con, quando=AGORA - dt.timedelta(days=3))
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 0 and h.chamadas == []


def test_a_mensagem_nunca_leva_o_token(con):
    _aviso(con)
    h = Http()
    enviar_avisos(con, ENV, AGORA, h)
    assert "segredo" not in json.dumps(h.chamadas[0][1])


def test_um_envio_por_aviso_com_limite_por_rodada(con):
    for i in range(12):
        _aviso(con, payload={"chave": str(i), "nome": f"C{i}", "vencimento": "2026-10-01", "valor": "R$ 1,00"})
    h = Http()
    assert enviar_avisos(con, ENV, AGORA, h) == 10  # no máximo 10 por rodada; o resto vai na próxima
