import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.correio import consulta
from gabi.db import conectar, migrar
from gabi.mcp import servidor
from gabi.mcp.ferramentas_trab import email_listar, resumo_da_manha
from gabi.trabalho import hoje as modulo_hoje

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 12, 10, 0, tzinfo=dt.timezone.utc)  # 07:00 BRT


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com", estado="sim"):
    return con.execute("insert into email_fonte(conta, provedor, estado) values (?, 'google', ?)", (conta, estado)).lastrowid


def _msg(con, f, ext, classe="importante", prioridade=2, estado="classificada", de="ana@x.com", assunto="Proposta", recebida="2026-10-12T08:00:00+00:00", motivo="cliente", atualizado=None):
    return con.execute("insert into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, classe, prioridade, motivo, estado, atualizado_em) values (?,?,?,?,?,?,?,?,?,?,?)",
                       (f, ext, ext + "t", de, assunto, recebida, classe, prioridade, motivo, estado, atualizado or recebida)).lastrowid


def test_importantes_ordena_emergencial_depois_prioridade_depois_data(con):
    f = _fonte(con)
    _msg(con, f, "a", "importante", 2, recebida="2026-10-12T09:00:00+00:00")
    _msg(con, f, "b", "importante", 3, recebida="2026-10-12T07:00:00+00:00")
    _msg(con, f, "c", "emergencial", 3, estado="alertada", recebida="2026-10-12T06:00:00+00:00")
    _msg(con, f, "d", "importante", 2, recebida="2026-10-12T09:30:00+00:00")
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == [3, 2, 4, 1]
    assert set(consulta.importantes(con, agora=AGORA)[0]) == {"id", "conta", "remetente", "assunto", "recebida_em", "classe", "prioridade", "motivo"}


def test_lixeira_lixo_normal_e_fonte_desligada_nao_entram_nos_importantes(con):
    f, g = _fonte(con), _fonte(con, "b@x.com", estado="nao")
    _msg(con, f, "na_lixeira", "lixo", 0, estado="na_lixeira"); _msg(con, f, "lixo", "lixo", 0); _msg(con, f, "normal", "normal", 1)
    _msg(con, f, "nova", None, None, estado="nova"); _msg(con, f, "restaurada", "importante", 2, estado="restaurada"); _msg(con, g, "desligada")
    assert consulta.importantes(con, agora=AGORA) == []


def test_importantes_respeita_o_limite(con):
    f = _fonte(con)
    for i in range(15):
        _msg(con, f, f"m{i}")
    assert len(consulta.importantes(con, agora=AGORA)) == 10 and len(consulta.importantes(con, limite=3, agora=AGORA)) == 3


def test_na_lixeira_lista_so_os_ultimos_30_dias(con):
    f, g = _fonte(con), _fonte(con, "b@x.com", estado="nao")
    _msg(con, f, "recente", "lixo", 0, estado="na_lixeira", atualizado="2026-10-10T10:00:00+00:00")
    _msg(con, f, "velha", "lixo", 0, estado="na_lixeira", atualizado="2026-08-01T10:00:00+00:00")
    _msg(con, g, "outra", "lixo", 0, estado="na_lixeira", atualizado="2026-10-10T10:00:00+00:00")
    _msg(con, f, "classificada", "lixo", 0)
    assert [m["id"] for m in consulta.na_lixeira(con, agora=AGORA)] == [3, 1]  # a conta desligada segue visível (aviso no painel)


def test_listar_filtra_prioridade_e_dias_e_exclui_lixo(con):
    f = _fonte(con)
    _msg(con, f, "alta", "importante", 3); _msg(con, f, "baixa", "normal", 1); _msg(con, f, "zero", "normal", 0); _msg(con, f, "lixo", "lixo", 0)
    _msg(con, f, "velha", "importante", 3, recebida="2026-09-01T00:00:00+00:00")
    assert [m["id"] for m in consulta.listar(con, AGORA, prioridade_min=1, dias=7)] == [1, 2]
    assert [m["id"] for m in consulta.listar(con, AGORA, prioridade_min=3, dias=7)] == [1]
    assert [m["id"] for m in consulta.listar(con, AGORA, prioridade_min=3, dias=60)] == [1, 5]


def _linha(texto):
    return next(l for l in texto["linhas"] if l.startswith("📧"))


def test_resumo_da_manha_cita_os_tres_primeiros_em_ordem(con):
    f = _fonte(con)
    _msg(con, f, "a", "emergencial", 3, estado="alertada", de="banco@x.com", assunto="Boleto vence hoje")
    _msg(con, f, "b", "importante", 3, de="ana@x.com", assunto="Proposta"); _msg(con, f, "c", "importante", 2, de="bia@x.com", assunto="Contrato")
    _msg(con, f, "d", "importante", 2, de="cid@x.com", assunto="Quarto item", recebida="2026-10-12T01:00:00+00:00")
    linha = _linha(resumo_da_manha(con, AGORA))
    t = "\n".join(resumo_da_manha(con, AGORA)["linhas"])
    assert "(4 importantes)" in linha and t.index("banco@x.com") < t.index("ana@x.com") < t.index("bia@x.com") and "cid@x.com" not in t and "+1 outros" in t


def test_resumo_da_manha_ignora_a_dispensada(con):
    f = _fonte(con)
    a = _msg(con, f, "a", "importante", 3, de="ana@x.com", assunto="Proposta"); _msg(con, f, "b", "importante", 2, de="bia@x.com", assunto="Contrato")
    con.execute("update email_msg set dispensada_em='2026-10-12T09:00:00+00:00' where id=?", (a,))
    t = "\n".join(resumo_da_manha(con, AGORA)["linhas"])
    assert "bia@x.com" in t and "ana@x.com" not in t


def test_resumo_sem_correio_diz_nenhum_e_com_muitos_cita_so_tres(con):
    assert "• Nenhum importante" in resumo_da_manha(con, AGORA)["linhas"]
    f = _fonte(con)
    for i in range(6):
        _msg(con, f, f"m{i}")
    r = resumo_da_manha(con, AGORA)["linhas"]
    assert sum(1 for l in r if l.startswith("• ") and "@" in l) == 3


def test_email_listar_respeita_limite_escopo_e_valores(con):
    assert servidor.ESCOPOS_FERRAMENTAS["email_listar"] == "trabalho"
    f = _fonte(con); _msg(con, f, "a", "importante", 3)
    r = email_listar(con, AGORA, 1, 7)
    assert [m["assunto"] for m in r["mensagens"]] == ["Proposta"] and r["dias"] == 7
    assert email_listar(con, AGORA, 0, 31)["dias"] == 31
    for args in ((1, 0), (1, 32), (4, 7), (-1, 7), (True, 7), ("1", 7), (1, 7.5)):
        with pytest.raises(ValueError):
            email_listar(con, AGORA, *args)


def test_hoje_traz_emergencial_nas_prioridades_antes_dos_outros(con):
    f = _fonte(con)
    _msg(con, f, "a", "emergencial", 3, estado="alertada", de="banco@x.com", assunto="Boleto vence hoje", motivo="prazo hoje")
    _msg(con, f, "b", "importante", 3)
    d = modulo_hoje.hoje(con, AGORA)
    assert d["prioridades"][0] == {"tipo": "email_emergencial", "titulo": "banco@x.com — Boleto vence hoje", "motivo": "prazo hoje", "ref": 1}
    assert [m["assunto"] for m in d["correio_importantes"]] == ["Boleto vence hoje", "Proposta"]
    assert modulo_hoje.hoje(con, AGORA, "e1")["prioridades"] == [] and modulo_hoje.hoje(con, AGORA, "e1")["correio_importantes"] == []


def test_importantes_so_olha_os_ultimos_dias_em_aberto_e_o_parametro_manda(con):
    f = _fonte(con)
    _msg(con, f, "hoje", "importante", 2, recebida="2026-10-12T08:00:00+00:00")
    _msg(con, f, "seis_dias", "emergencial", 3, estado="alertada", recebida="2026-10-06T12:00:00+00:00")
    _msg(con, f, "oito_dias", "emergencial", 3, estado="alertada", recebida="2026-10-04T08:00:00+00:00")
    _msg(con, f, "tres_semanas", "importante", 3, recebida="2026-09-21T08:00:00+00:00")
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == [2, 1]  # padrão 7 dias: o resolvido há semanas não ofusca o novo
    con.execute("insert into parametro(chave, valor) values ('email.dias_em_aberto', '30')")
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == [2, 3, 4, 1]  # emergenciais (mais recente primeiro), depois as importantes
    con.execute("update parametro set valor='\"muitos\"' where chave='email.dias_em_aberto'")
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == [2, 1]  # parâmetro inválido cai no padrão


def test_resumo_e_hoje_nao_trazem_emergencial_antigo(con):
    f = _fonte(con)
    _msg(con, f, "velho", "emergencial", 3, estado="alertada", recebida="2026-09-01T08:00:00+00:00")
    assert modulo_hoje.hoje(con, AGORA)["prioridades"] == [] and all(not l.startswith("E-mail:") for l in resumo_da_manha(con, AGORA)["linhas"])


def test_lixo_sugerido_lista_o_lixo_nao_movido_so_de_conta_liberada(con):
    f, g = _fonte(con), _fonte(con, "b@x.com", estado="nao")
    con.execute("update email_fonte set lixeira=1 where id=?", (f,))
    _msg(con, f, "sug", "lixo", 0, motivo="promoção", de="promo@loja.com", assunto="Oferta")
    _msg(con, f, "movida", "lixo", 0, estado="na_lixeira"); _msg(con, f, "voltou", "lixo", 0, estado="restaurada")
    _msg(con, f, "imp", "importante", 2); _msg(con, g, "desl", "lixo", 0)
    _msg(con, f, "velha", "lixo", 0, recebida="2026-08-01T08:00:00+00:00")
    r = consulta.lixo_sugerido(con, agora=AGORA)
    assert [(m["assunto"], m["motivo"], m["conta_lixeira"]) for m in r] == [("Oferta", "promoção", 1)]
    assert {"id", "conta", "remetente", "assunto", "motivo", "recebida_em"} <= set(r[0])


def test_dispensada_sai_das_listas_e_do_resumo_da_manha_e_desfazer_volta(con):
    f = _fonte(con)
    a = _msg(con, f, "a", "importante", 3); b = _msg(con, f, "b", "emergencial", 3, estado="alertada"); _msg(con, f, "c", "normal", 1)
    assert len(consulta.importantes(con, agora=AGORA)) == 2 and len(consulta.listar(con, AGORA)) == 3
    con.execute("update email_msg set dispensada_em='2026-10-12T09:00:00+00:00' where id in (?,?)", (a, b))
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == []
    assert len(consulta.listar(con, AGORA)) == 1
    assert {m["id"] for m in consulta.dispensadas(con, agora=AGORA)} == {a, b}
    con.execute("update email_msg set dispensada_em=null where id=?", (a,))
    assert [m["id"] for m in consulta.importantes(con, agora=AGORA)] == [a]


def test_na_lixeira_continua_visivel_com_a_conta_desligada_e_avisa(con):
    f, g = _fonte(con), _fonte(con, "b@x.com", estado="nao")
    _msg(con, f, "ok", "lixo", 0, estado="na_lixeira", atualizado="2026-10-10T10:00:00+00:00")
    _msg(con, g, "desl", "lixo", 0, estado="na_lixeira", atualizado="2026-10-11T10:00:00+00:00")
    r = {m["conta"]: m["conta_desligada"] for m in consulta.na_lixeira(con, agora=AGORA)}
    assert r == {"a@x.com": False, "b@x.com": True}
