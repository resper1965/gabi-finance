"""Projetos (ADR-034): pessoas, dinheiro, fatos e o resumo `ver`. Consome: gabi.projetos. AGORA = 27/10/2026 12:00 BRT."""
import datetime as dt
from pathlib import Path

import pytest

from gabi import atividades, projetos
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(id, externo_id) values (1, 'c1')")
    return c


def _p(con, **kw):
    return projetos.criar(con, AGORA, "hermes", "hermes", "Carro", **kw)["id"]


def _lanc(con, valor, id_=1):
    con.execute("insert into lancamento(id, conta_id, externo_id, data, valor_centavos) values (?,1,?,'2026-10-20',?)", (id_, f"e{id_}", valor))
    return id_


def test_pessoa_com_papel_e_ligacao_opcional_a_pessoa_da_familia(con):
    con.execute("insert into pessoa(id, nome) values ('louise','Louise')")
    p = _p(con)
    a = projetos.adicionar_pessoa(con, AGORA, "hermes", "hermes", p, "Seu Jorge", papel="mecânico", contato="11 99999-0000")
    b = projetos.adicionar_pessoa(con, AGORA, "hermes", "hermes", p, "Louise", pessoa_id="louise")
    assert (a["nome"], a["papel"], a["contato"], a["pessoa_id"]) == ("Seu Jorge", "mecânico", "11 99999-0000", None) and b["pessoa_id"] == "louise"
    with pytest.raises(ValueError):
        projetos.adicionar_pessoa(con, AGORA, "hermes", "hermes", p, "  ")
    with pytest.raises(ValueError):
        projetos.adicionar_pessoa(con, AGORA, "hermes", "hermes", p, "X", pessoa_id="nao-existe")


def test_gasto_manual_soma_no_projeto(con):
    p = _p(con, orcamento_centavos=500000)
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, valor_centavos=120050, descricao="peça")
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, valor_centavos=30000, data="2026-10-01")
    v = projetos.ver(con, AGORA, p)
    assert (v["orcamento"], v["gasto"], v["saldo"]) == ("5000.00", "1500.50", "3499.50")


def test_gasto_ligado_a_lancamento_usa_o_valor_absoluto_do_lancamento(con):
    p = _p(con, orcamento_centavos=100000)
    _lanc(con, -45000)
    g = projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, lancamento_id=1, descricao="oficina")
    assert g["lancamento_id"] == 1 and projetos.ver(con, AGORA, p)["gasto"] == "450.00"


def test_gasto_com_lancamento_inexistente_ou_dois_valores_recusa(con):
    p = _p(con)
    _lanc(con, -100)
    for kw in ({"lancamento_id": 99}, {"lancamento_id": 1, "valor_centavos": 100}, {}, {"valor_centavos": 0}, {"valor_centavos": -5}):
        with pytest.raises(ValueError):
            projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, **kw)
    assert con.execute("select count(*) from projeto_gasto").fetchone()[0] == 0


def test_ver_com_lancamento_removido_ou_sem_valor_soma_zero_e_nao_quebra(con):
    p = _p(con, orcamento_centavos=10000)
    _lanc(con, -2500)
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, lancamento_id=1)
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, valor_centavos=1000)
    con.execute("delete from lancamento where id=1")
    con.execute("insert into projeto_gasto(projeto_id, descricao, criado_em) values (?, 'sem valor', 'x')", (p,))
    v = projetos.ver(con, AGORA, p)
    assert v["gasto"] == "10.00" and v["saldo"] == "90.00"


def test_ver_sem_orcamento_devolve_none(con):
    p = _p(con)
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, valor_centavos=1000)
    v = projetos.ver(con, AGORA, p)
    assert v["orcamento"] is None and v["saldo"] is None and v["gasto"] == "10.00"
    assert "None" not in str(v["gasto"]) and projetos.ver(con, AGORA, _p(con))["gasto"] == "0.00"


def test_ver_saldo_negativo_quando_estoura(con):
    p = _p(con, orcamento_centavos=10000)
    projetos.adicionar_gasto(con, AGORA, "hermes", "hermes", p, valor_centavos=12550)
    assert projetos.ver(con, AGORA, p)["saldo"] == "-25.50"


def test_fato_grava_data_hoje_e_origem_e_aceita_acento_emoji_aspas(con):
    p = _p(con)
    texto = 'O mecânico disse: "prazo dia 20" 🚗'
    f = projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, texto, pessoa_nome="Seu Jorge")
    assert f["texto"] == texto and f["data"] == "2026-10-27" and f["origem"] == "hermes" and f["pessoa_nome"] == "Seu Jorge"
    assert projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "outro", data="2026-10-01")["data"] == "2026-10-01"
    with pytest.raises(ValueError):
        projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "x", data="ontem")
    with pytest.raises(ValueError):
        projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "x", anexo_id=99)


def test_fato_vazio_ou_longo_recusa(con):
    p = _p(con)
    for t in ("", "   ", "a" * 1001):
        with pytest.raises(ValueError):
            projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, t)
    assert projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "a" * 1000)["id"]


def test_listar_fatos_busca_sem_acento(con):
    p = _p(con)
    projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "Prazo da oficina é dia 20", data="2026-10-20")
    projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, "Ficou combinado pagar em duas vezes", data="2026-10-25")
    todos = projetos.listar_fatos(con, p)
    assert [f["data"] for f in todos] == ["2026-10-25", "2026-10-20"]
    assert [f["texto"] for f in projetos.listar_fatos(con, p, texto="OFICINA é")] == ["Prazo da oficina é dia 20"]
    assert [f["texto"] for f in projetos.listar_fatos(con, p, texto="combínado")] == ["Ficou combinado pagar em duas vezes"]
    assert len(projetos.listar_fatos(con, p, limite=1)) == 1


def test_ver_traz_proximas_bloqueadas_e_atrasadas(con):
    p = _p(con, objetivo="trocar o motor", atividades=[
        {"texto": "orçamento", "vence": "2026-10-30"}, {"texto": "aprovar", "depois_de": 1}, {"texto": "ligar pro seguro", "vence": "2026-10-27"}, {"texto": "sem data"}])
    atividades.criar(con, AGORA, "hermes", "hermes", "fora do projeto")
    for n in range(5):
        projetos.registrar_fato(con, AGORA, "hermes", "hermes", p, f"fato {n}", data=f"2026-10-0{n + 1}")
    con.execute("insert into anexo(tipo, sha256, recebido_em, projeto_id) values ('imagem','a','x',?)", (p,))
    con.execute("update atividade set vence_em='2026-10-20T03:00:00+00:00' where texto='ligar pro seguro'")
    v = projetos.ver(con, AGORA, p)
    assert v["objetivo"] == "trocar o motor" and v["status"] == "ativo" and v["progresso"] == {"feitas": 0, "total": 4}
    assert [a["texto"] for a in v["proximas"]] == ["ligar pro seguro", "orçamento", "sem data"]
    assert [a["texto"] for a in v["bloqueadas"]] == ["aprovar"]
    assert [a["texto"] for a in v["atrasadas"]] == ["ligar pro seguro"]
    assert len(v["fatos_recentes"]) == 5 and v["fatos_recentes"][0]["texto"] == "fato 4" and v["anexos"] == 1 and v["pessoas"] == []
    with pytest.raises(LookupError):
        projetos.ver(con, AGORA, 999)


def test_ver_bloqueada_diz_o_que_espera_e_lista_os_anexos(con):
    p = _p(con, atividades=[{"texto": "pedir orçamento"}, {"texto": "aprovar", "depois_de": 1}])
    v = projetos.ver(con, AGORA, p)
    assert [(a["texto"], a["espera"]) for a in v["bloqueadas"]] == [("aprovar", "pedir orçamento")] and "espera" not in v["proximas"][0]
    con.execute("insert into anexo(tipo, arquivo, sha256, transcricao, recebido_em, projeto_id) values ('audio','aa/a.ogg','a','oi','2026-10-27T10:00:00+00:00',?)", (p,))
    con.execute("insert into anexo(tipo, paperless_id, recebido_em, projeto_id) values ('documento', 9, '2026-10-26T10:00:00+00:00', ?)", (p,))
    v = projetos.ver(con, AGORA, p)
    assert v["anexos"] == 2 and [(a["tipo"], a["transcricao"], a["paperless_id"]) for a in v["anexos_itens"]] == [("audio", "oi", None), ("documento", None, 9)]
