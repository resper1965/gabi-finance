import datetime as dt
import pathlib
import sqlite3
import re

from gabi.envelope import HORAS_RODADAS, proxima_rodada

UTC = dt.timezone.utc


def test_proxima_rodada_antes_das_6_e_das_14_e_na_virada_do_dia():
    # 09:00 UTC = 06:00 BRT em ponto: a de 06h já passou, a próxima é 14h BRT = 17:00 UTC
    assert proxima_rodada(dt.datetime(2026, 10, 9, 9, 0, tzinfo=UTC)) == "2026-10-09T17:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 8, 59, tzinfo=UTC)) == "2026-10-09T09:00:00Z"
    # depois das 14h BRT: amanhã 06h BRT
    assert proxima_rodada(dt.datetime(2026, 10, 9, 17, 0, tzinfo=UTC)) == "2026-10-10T09:00:00Z"
    assert proxima_rodada(dt.datetime(2026, 10, 9, 23, 30, tzinfo=UTC)) == "2026-10-10T09:00:00Z"


def test_horas_batem_com_o_timer_instalado():
    timer = (pathlib.Path(__file__).parent.parent / "deploy" / "gabi-brain-extratos.timer").read_text()
    horas = re.search(r"OnCalendar=\S+ (\d\d(?:,\d\d)*):00:00 America/Sao_Paulo", timer).group(1)
    assert tuple(int(h) for h in horas.split(",")) == HORAS_RODADAS


# ---------------- frescor por fonte (fontes sem conferência) ----------------
import pytest  # noqa: E402

from gabi.db import conectar, migrar  # noqa: E402
from gabi.envelope import envelope  # noqa: E402

MIGR = pathlib.Path(__file__).parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _r(con, fonte, horas, status="ok", conferida=0):
    fim = (AGORA - dt.timedelta(hours=horas)).isoformat()
    con.execute("insert into rodada(fonte, inicio, fim, status, conferida) values (?,?,?,?,?)", (fonte, fim, fim, status, conferida))


def _estados(env):
    return {f["nome"]: f["estado"] for f in env["fontes"]}


def _producao(con):
    _r(con, "open-finance", 2, conferida=1)
    _r(con, "notas-nibo", 3)
    _r(con, "comprovantes-paperless", 3)
    _r(con, "trabalho", 1)  # ninguém liberado: não conta


def test_producao_fontes_sem_conferencia_nao_geram_falso_alarme(con):
    _producao(con)
    e = envelope(con, None, AGORA)
    assert e["desatualizado"] is False
    assert e["dados_ate"] is not None
    assert _estados(e) == {"comprovantes-paperless": "ok", "notas-nibo": "ok", "open-finance": "ok"}


def test_nibo_com_50h_esta_parada_e_desatualiza(con):
    _producao(con)
    con.execute("delete from rodada where fonte='notas-nibo'")
    _r(con, "notas-nibo", 50)
    e = envelope(con, None, AGORA)
    assert _estados(e)["notas-nibo"] == "parada"
    assert e["desatualizado"] is True


def test_nibo_ultima_tentativa_com_erro(con):
    _producao(con)
    _r(con, "notas-nibo", 1, status="erro")
    e = envelope(con, None, AGORA)
    assert _estados(e)["notas-nibo"] == "erro"
    assert e["desatualizado"] is True


def test_fonte_que_nunca_rodou_ok_fica_nao_conferida_e_desatualiza(con):
    _producao(con)
    con.execute("delete from rodada where fonte='comprovantes-paperless'")
    _r(con, "comprovantes-paperless", 1, status="rodando")
    e = envelope(con, None, AGORA)
    assert _estados(e)["comprovantes-paperless"] == "nao_conferida"
    assert e["desatualizado"] is True and e["dados_ate"] is None


def test_open_finance_sem_conferencia_continua_nao_conferida(con):
    _r(con, "open-finance", 1, conferida=0)
    e = envelope(con, None, AGORA)
    assert _estados(e)["open-finance"] == "nao_conferida"
    assert e["desatualizado"] is True


def test_trabalho_conta_quando_ha_caixa_liberada(con):
    _producao(con)
    con.execute("insert into caixa_email(endereco, provedor, estado) values ('a@b.c','graph','sim')")
    assert _estados(envelope(con, None, AGORA))["trabalho"] == "ok"
    con.execute("delete from rodada where fonte='trabalho'")
    _r(con, "trabalho", 30, status="ok")
    e = envelope(con, None, AGORA)
    assert _estados(e)["trabalho"] == "parada" and e["desatualizado"] is True


def test_saldos_e_exportacao_nao_entram(con):
    _producao(con)
    _r(con, "open-finance-saldos", 99)
    _r(con, "exportacao", 99)
    assert "exportacao" not in _estados(envelope(con, None, AGORA))


# ---------------- fontes esperadas, tabela única, minors ----------------
def test_banco_novo_so_com_open_finance_lista_as_esperadas_como_nao_conferidas(con):
    _r(con, "open-finance", 1, conferida=1)
    e = envelope(con, None, AGORA)
    assert e["desatualizado"] is True
    assert _estados(e) == {"comprovantes-paperless": "nao_conferida", "notas-nibo": "nao_conferida", "open-finance": "ok"}
    _r(con, "notas-nibo", 1)
    _r(con, "comprovantes-paperless", 1)
    e = envelope(con, None, AGORA)
    assert e["desatualizado"] is False and set(_estados(e).values()) == {"ok"}


def test_trabalho_em_uso_sem_nenhuma_rodada_aparece_nao_conferida(con):
    _producao(con)
    con.execute("delete from rodada where fonte='trabalho'")
    con.execute("insert into caixa_email(endereco, provedor, estado) values ('a@b.c','graph','sim')")
    e = envelope(con, None, AGORA)
    assert _estados(e)["trabalho"] == "nao_conferida" and e["desatualizado"] is True


def test_fonte_nao_declarada_aparece_mas_nunca_desatualiza(con):
    _producao(con)
    _r(con, "futura", 900)
    e = envelope(con, None, AGORA)
    assert _estados(e)["futura"] == "ok" and e["desatualizado"] is False
    _r(con, "futura", 1, status="erro")
    e = envelope(con, None, AGORA)
    assert _estados(e)["futura"] == "erro" and e["desatualizado"] is False


def test_toda_fonte_registrada_no_codigo_esta_declarada_em_FONTES():
    import ast
    from gabi.envelope import FONTES
    achadas = set()
    for f in (pathlib.Path(__file__).parent.parent / "gabi").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "registrar_rodada" \
                    and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                achadas.add(n.args[1].value)
    assert achadas and achadas <= set(FONTES), achadas - set(FONTES)


def test_trabalho_fora_com_tabelas_vazias_ou_agenda_fonte_ausente(con):
    _producao(con)
    assert "trabalho" not in _estados(envelope(con, None, AGORA))  # caixa_email vazia, agenda_fonte inexistente


def test_erro_de_banco_que_nao_e_tabela_ausente_nao_e_engolido(con):
    from gabi.envelope import _trabalho_em_uso

    class Trava:
        def execute(self, *a):
            raise sqlite3.OperationalError("database is locked")
    with pytest.raises(sqlite3.OperationalError):
        _trabalho_em_uso(Trava())


def test_limite_diario_e_30h(con):
    _producao(con)
    con.execute("delete from rodada where fonte='notas-nibo'")
    _r(con, "notas-nibo", 31)
    assert _estados(envelope(con, None, AGORA))["notas-nibo"] == "parada"


def test_open_finance_conferida_ha_4_dias_manda_no_dados_ate(con):
    _producao(con)
    con.execute("delete from rodada where fonte='open-finance'")
    _r(con, "open-finance", 96, conferida=1)
    e = envelope(con, None, AGORA)
    assert e["desatualizado"] is True and e["dados_ate"] == "2026-10-07T12:00:00Z"


# ---------------- agenda: fonte própria de frescor ----------------
def test_agenda_conta_so_com_fonte_liberada_e_pela_propria_rodada(con):
    _producao(con)
    _r(con, "agenda", 1, status="ok")
    assert "agenda" not in _estados(envelope(con, None, AGORA))  # ninguém liberado: não conta
    con.execute("insert into agenda_fonte(conta, provedor, estado) values ('a@x.com','google','sim')")
    e = envelope(con, None, AGORA)
    assert _estados(e)["agenda"] == "ok" and "trabalho" not in _estados(e)  # liberar agenda NÃO liga o 'trabalho' (e-mail)
    con.execute("delete from rodada where fonte='agenda'")
    _r(con, "agenda", 13, status="ok")
    e = envelope(con, None, AGORA)
    assert _estados(e)["agenda"] == "parada" and e["desatualizado"] is True


def test_agenda_liberada_sem_nenhuma_rodada_aparece_nao_conferida(con):
    _producao(con)
    con.execute("insert into agenda_fonte(conta, provedor, estado) values ('a@x.com','google','sim')")
    e = envelope(con, None, AGORA)
    assert _estados(e)["agenda"] == "nao_conferida" and e["desatualizado"] is True


# ---------------- correio: fonte própria de frescor ----------------
def test_correio_so_conta_com_fonte_liberada_e_pela_propria_rodada(con):
    _producao(con)
    _r(con, "correio", 1, status="ok")
    assert "correio" not in _estados(envelope(con, None, AGORA))  # nenhuma conta liberada: não conta
    con.execute("insert into email_fonte(conta, provedor, estado) values ('a@x.com','google','sim')")
    e = envelope(con, None, AGORA)
    assert _estados(e)["correio"] == "ok" and "trabalho" not in _estados(e) and "agenda" not in _estados(e)  # liberar e-mail não liga os outros
    con.execute("delete from rodada where fonte='correio'")
    _r(con, "correio", 13, status="ok")
    e = envelope(con, None, AGORA)
    assert _estados(e)["correio"] == "parada" and e["desatualizado"] is True


def test_correio_liberado_sem_nenhuma_rodada_aparece_nao_conferida(con):
    _producao(con)
    con.execute("insert into email_fonte(conta, provedor, estado) values ('a@x.com','google','sim')")
    e = envelope(con, None, AGORA)
    assert _estados(e)["correio"] == "nao_conferida" and e["desatualizado"] is True
