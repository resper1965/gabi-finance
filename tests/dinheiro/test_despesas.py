import datetime as dt
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import contas_pagar as cp, despesas, repositorio
from tests.rotas.test_cadastros_api import banco, cli, req  # noqa: F401  (fixtures do cliente HTTP)

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def test_migracao_tipo_e_dispensado(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('x','X','X','dia:5')")
    assert con.execute("select tipo from compromisso_linha where id='x'").fetchone()[0] == "fixa"
    con.execute("insert into valor_do_mes(mes, compromisso, tipo) values ('2026-10','x','dispensado')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update compromisso_linha set tipo='outra' where id='x'")


# ---------------- Task 2: criar e listar ----------------
AGORA = dt.datetime(2026, 10, 26, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _fixa(con, **kw):
    return despesas.criar_fixa(con, AGORA, "ricardo", "painel", {"nome": "Escola", "valor_padrao": "3000.00", "vencimento": "dia:6", **kw})


def test_criar_fixa_gera_em_a_pagar(con):
    item = _fixa(con)
    assert item["id"] == "escola" and item["valor"] == "3000.00" and item["tipo"] == "fixa" and item["situacao"] == "ativa"
    ocs = dict(con.execute("select id, valor_centavos from compromisso where linha_id='escola'").fetchall())
    assert ocs["escola:2026-10"] == 300000 and ocs["escola:2026-11"] == 300000
    assert con.execute("select o_que, quem, origem from decisao").fetchone()[:] == ("despesa escola criada (fixa)", "ricardo", "painel")
    assert con.execute("select extrato, valido_de from compromisso_linha where id='escola'").fetchone()[:] == ("Escola", "2026-10")


def test_criar_avulsa_so_um_mes(con):
    item = despesas.criar_avulsa(con, AGORA, "ricardo", "hermes", {"nome": "Dentista", "valor_padrao": "450.00"}, "2026-11-20")
    assert item["id"] == "dentista" and item["versao_id"] == "dentista-202611" and item["tipo"] == "avulsa" and item["vencimento"] == "dia:20"
    r = con.execute("select tipo, valido_de, valido_ate from compromisso_linha where id='dentista-202611'").fetchone()
    assert r[:] == ("avulsa", "2026-11", "2026-11")
    ids = [x[0] for x in con.execute("select id from compromisso where linha_id like 'dentista%'")]
    assert ids and all(i.endswith(":2026-11") for i in ids)


def test_criar_invalido(con):
    with pytest.raises(ValueError):
        _fixa(con, vencimento="dia:40")
    with pytest.raises(ValueError):
        despesas.criar_fixa(con, AGORA, "r", "painel", {"nome": " "})
    assert con.execute("select count(*) from compromisso_linha").fetchone()[0] == 0


def test_listar_por_tipo_e_situacao(con):
    _fixa(con)
    despesas.criar_avulsa(con, AGORA, "r", "painel", {"nome": "Dentista", "valor_padrao": "450.00"}, "2026-11-20")
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valido_ate) values ('velha','Velha','Velha','dia:5','2026-08')")
    todos = despesas.listar(con, AGORA.date())
    assert {i["id"] for i in todos} == {"escola", "dentista", "velha"}
    assert [i["id"] for i in despesas.listar(con, AGORA.date(), tipo="avulsa")] == ["dentista"]
    assert [i["id"] for i in despesas.listar(con, AGORA.date(), situacao="encerrada")] == ["velha"]
    esc = next(i for i in todos if i["id"] == "escola")
    assert esc["proximo_vencimento"] == "2026-11-06" and esc["versoes"][0]["id"] == "escola"
    with pytest.raises(LookupError):
        despesas.serie_de(con, "nada")


def test_cadastros_compromissos_continua(cli):
    r = req(cli, "POST", "/api/v1/cadastros/compromissos", {"nome": "X", "extrato": "X", "vencimento": "dia:40"})
    assert r.status_code == 400


def _avulsa(con, nome, data):
    return despesas.criar_avulsa(con, AGORA, "r", "painel", {"nome": nome, "valor_padrao": "100.00"}, data)


def test_avulsas_de_mesmo_nome_sao_series_distintas(con):
    a, b = _avulsa(con, "Dentista", "2026-11-20"), _avulsa(con, "Dentista", "2026-12-10")
    assert a["id"] != b["id"] and len(a["versoes"]) == len(b["versoes"]) == 1
    assert {i["id"] for i in despesas.listar(con, AGORA.date())} == {a["id"], b["id"]}


def test_avulsa_com_nome_de_fixa_existente(con):
    _fixa(con)
    av = _avulsa(con, "Escola", "2026-11-20")
    assert av["id"] != "escola" and av["tipo"] == "avulsa"
    assert [v["id"] for v in despesas.serie_de(con, "escola")] == ["escola"]


def test_fixa_depois_de_avulsa_de_mesmo_nome(con):
    _avulsa(con, "Dentista", "2026-11-20")
    f = despesas.criar_fixa(con, AGORA, "r", "painel", {"nome": "Dentista", "valor_padrao": "100.00", "vencimento": "dia:6"})
    assert f["tipo"] == "fixa" and f["id"] == "dentista-2"


def test_hoje_em_brt_mesmo_com_agora_em_utc(con):
    utc = dt.datetime(2026, 11, 1, 1, 0, tzinfo=dt.timezone.utc)  # 31/10 22:00 em Brasília
    despesas.criar_fixa(con, utc, "r", "painel", {"nome": "Luz", "valor_padrao": "10.00", "vencimento": "dia:6"})
    assert con.execute("select valido_de from compromisso_linha where id='luz'").fetchone()[0] == "2026-10"


# ---------------- Task 3: mudar, mês, dispensar, encerrar, excluir ----------------
AGORA3 = dt.datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _luz(con, desde_sempre=False):
    item = despesas.criar_fixa(con, AGORA3, "ricardo", "painel", {"nome": "Luz", "valor_padrao": "200.00", "vencimento": "dia:10"})
    if desde_sempre:
        con.execute("update compromisso_linha set valido_de=null where id='luz'")
    return item


def _comp(con, id_):
    return con.execute("select valor_centavos, vencimento, estado from compromisso where id=?", (id_,)).fetchone()


def _pagar(con, linha, mes):
    """Baixa manual no Valores do mês (o mesmo caminho da planilha) e recalcula: a ocorrência fica `pago`."""
    con.execute("insert into valor_do_mes(mes, compromisso, tipo, valor_centavos, data_pagamento) values (?,?,'pago',20000,?)", (mes, linha, f"{mes}-10"))
    cp.atualizar_compromissos(con, AGORA3.date(), AGORA3)


def _ocorrencia(con, id_, estado):
    """Ocorrência antiga (fora da janela de geração) gravada como a rodada de um mês passado teria deixado."""
    con.execute("insert into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, valor_centavos, estado) "
                "values (?, 'planilha', 'luz', 'Luz', ?, ?, 20000, ?)", (id_, f"{id_[-7:]}-10", f"{id_[-7:]}-10", estado))


def test_mudar_vale_do_mes_em_curso_sem_pagamento(con):
    _luz(con)
    r = despesas.mudar(con, AGORA3, "ricardo", "painel", "luz", {"valor_padrao": "250.00"})
    assert r["a_partir"] == "2026-10" and r["nova_versao"] is False and r["valor"] == "250.00"
    assert [v["id"] for v in despesas.serie_de(con, "luz")] == ["luz"]
    assert _comp(con, "luz:2026-10")[0] == 25000


def test_mudar_mes_pago_vale_do_proximo(con):
    _luz(con)
    _pagar(con, "luz", "2026-10")
    assert despesas.mes_pago(con, "luz", "2026-10") and despesas.mes_inicial(con, "luz", AGORA3.date()) == "2026-11"
    r = despesas.mudar(con, AGORA3, "ricardo", "painel", "luz", {"valor_padrao": "250.00"})
    assert r["a_partir"] == "2026-11" and r["nova_versao"] is True and r["versao_id"] == "luz-202611"
    assert con.execute("select valido_ate from compromisso_linha where id='luz'").fetchone()[0] == "2026-10"
    assert con.execute("select valido_de, valido_ate, valor_padrao_centavos from compromisso_linha where id='luz-202611'").fetchone()[:] == ("2026-11", None, 25000)
    assert _comp(con, "luz:2026-10")[0] == 20000
    assert _comp(con, "luz-202611:2026-11")[0] == 25000


def test_mudar_duas_vezes_mesmo_inicio(con):
    _luz(con)
    _pagar(con, "luz", "2026-10")
    despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "250.00"})
    r = despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "260.00", "vencimento": "dia:12"})
    assert r["nova_versao"] is False and r["a_partir"] == "2026-11"
    assert [v["id"] for v in despesas.serie_de(con, "luz")] == ["luz", "luz-202611"]
    assert con.execute("select valor_padrao_centavos, vencimento from compromisso_linha where id='luz-202611'").fetchone()[:] == (26000, "dia:12")


def test_mudar_a_partir_explicito(con):
    _luz(con)
    r = despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "300.00"}, a_partir="2026-12")
    assert r["a_partir"] == "2026-12" and r["nova_versao"] is True and r["versao_id"] == "luz-202612"
    assert con.execute("select valido_ate from compromisso_linha where id='luz'").fetchone()[0] == "2026-11"
    assert _comp(con, "luz:2026-10")[0] == 20000 and _comp(con, "luz:2026-11")[0] == 20000
    with pytest.raises(ValueError):
        despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "1.00"}, a_partir="2026-09")  # mês passado nunca muda
    with pytest.raises(ValueError):
        despesas.mudar(con, AGORA3, "r", "painel", "luz", {"cor": "azul"})


def test_mudar_mes_so_valor_e_so_data(con):
    _luz(con)
    despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-11", valor="180.00")
    assert _comp(con, "luz:2026-11")[:2] == (18000, "2026-11-10")
    despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-11", vencimento="2026-11-15")
    assert _comp(con, "luz:2026-11")[:2] == (18000, "2026-11-15")
    assert con.execute("select count(*) from valor_do_mes where compromisso='luz' and mes='2026-11' and tipo='valor'").fetchone()[0] == 1
    assert _comp(con, "luz:2026-10")[0] == 20000
    with pytest.raises(ValueError):
        despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-11")


def test_dispensar_some_e_desfazer_volta(con):
    _luz(con)
    despesas.dispensar_mes(con, AGORA3, "r", "painel", "luz", "2026-11")
    assert _comp(con, "luz:2026-11") is None and _comp(con, "luz:2026-10") is not None
    assert con.execute("select tipo from valor_do_mes where compromisso='luz' and mes='2026-11'").fetchone()[0] == "dispensado"
    despesas.desfazer_dispensa(con, AGORA3, "r", "painel", "luz", "2026-11")
    assert _comp(con, "luz:2026-11")[0] == 20000
    assert con.execute("select count(*) from valor_do_mes where compromisso='luz'").fetchone()[0] == 0


def test_dispensar_mes_pago_recusa(con):
    _luz(con)
    _pagar(con, "luz", "2026-10")
    with pytest.raises(ValueError, match="mês já pago"):
        despesas.dispensar_mes(con, AGORA3, "r", "painel", "luz", "2026-10")
    assert _comp(con, "luz:2026-10")[2] == "pago"


def test_rodada_pula_mes_dispensado(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_padrao_centavos) values ('agua','Água','Agua','dia:5',5000)")
    con.execute("insert into valor_do_mes(mes, compromisso, tipo) values ('2026-11','agua','dispensado')")
    leitura = repositorio.ler_leitura(con)
    assert leitura["dispensados"] == [{"compromisso": "agua", "mes": "2026-11"}]
    assert all(v["tipo"] != "dispensado" for v in leitura["valores"])
    cp.atualizar_compromissos(con, AGORA3.date(), AGORA3)
    ids = {r[0] for r in con.execute("select id from compromisso where linha_id='agua'")}
    assert ids == {"agua:2026-10"}


def test_encerrar_tira_nao_pagas_e_mantem_pagas(con):
    _luz(con, desde_sempre=True)
    cp.atualizar_compromissos(con, AGORA3.date(), AGORA3)
    _ocorrencia(con, "luz:2026-08", "pago")
    r = despesas.encerrar(con, AGORA3, "r", "painel", "luz")
    assert r == {"id": "luz", "ultimo_mes": "2026-09"}
    assert _comp(con, "luz:2026-10") is None and _comp(con, "luz:2026-11") is None
    assert _comp(con, "luz:2026-08")[2] == "pago"
    assert con.execute("select valido_ate, excluido_em from compromisso_linha where id='luz'").fetchone()[:] == ("2026-09", None)
    assert despesas.listar(con, AGORA3.date(), situacao="encerrada")[0]["id"] == "luz"


def test_encerrar_tira_atrasada_antiga(con):
    _luz(con, desde_sempre=True)
    _ocorrencia(con, "luz:2026-09", "atrasado")
    despesas.encerrar(con, AGORA3, "r", "painel", "luz", ultimo_mes="2026-08")
    assert _comp(con, "luz:2026-09") is None and _comp(con, "luz:2026-10") is None


def test_encerrar_antes_de_comecar(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_padrao_centavos, valido_de) values ('luz','Luz','Luz','dia:10',20000,'2026-12')")
    r = despesas.encerrar(con, AGORA3, "r", "painel", "luz", ultimo_mes="2026-11")
    assert r == {"id": "luz", "ultimo_mes": "2026-11"}
    assert con.execute("select excluido_em from compromisso_linha where id='luz'").fetchone()[0] is not None


def test_excluir_sem_pagamento_apaga(con):
    _luz(con)
    r = despesas.excluir(con, AGORA3, "r", "painel", "luz")
    assert r == {"id": "luz", "excluida": True, "encerrada": False}
    assert con.execute("select count(*) from compromisso where linha_id like 'luz%'").fetchone()[0] == 0
    assert con.execute("select count(*) from compromisso_linha where id='luz' and excluido_em is not null").fetchone()[0] == 1
    with pytest.raises(LookupError):
        despesas.serie_de(con, "luz")


def test_excluir_com_pagamento_encerra(con):
    _luz(con, desde_sempre=True)
    _ocorrencia(con, "luz:2026-08", "pago")
    r = despesas.excluir(con, AGORA3, "r", "painel", "luz")
    assert r == {"id": "luz", "excluida": False, "encerrada": True, "ultimo_mes": "2026-09"}
    assert con.execute("select excluido_em from compromisso_linha where id='luz'").fetchone()[0] is None
    assert _comp(con, "luz:2026-08")[2] == "pago" and _comp(con, "luz:2026-10") is None


def test_decisao_registrada(con):
    _luz(con)
    despesas.mudar(con, AGORA3, "ricardo", "hermes", "luz", {"valor_padrao": "250.00"})
    despesas.dispensar_mes(con, AGORA3, "ricardo", "hermes", "luz", "2026-11")
    despesas.encerrar(con, AGORA3, "ricardo", "hermes", "luz", ultimo_mes="2026-12")
    linhas = con.execute("select quem, origem, o_que from decisao order by id").fetchall()[1:]
    assert len(linhas) == 3 and all(l[0] == "ricardo" and l[1] == "hermes" for l in linhas)
    assert "luz" in linhas[0][2] and "2026-11" in linhas[1][2] and "2026-12" in linhas[2][2]


# ---------------- Task 3, correção 1 ----------------
def test_mudar_leva_dispensa_e_valor_do_mes_para_versao_nova(con):
    _luz(con)
    despesas.dispensar_mes(con, AGORA3, "r", "painel", "luz", "2026-11")
    despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-11", valor="1.00")
    r = despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "300.00"}, a_partir="2026-11")
    assert r["versao_id"] == "luz-202611"
    assert _comp(con, "luz-202611:2026-11") is None and _comp(con, "luz:2026-11") is None
    assert {tuple(x) for x in con.execute("select compromisso, tipo from valor_do_mes where mes='2026-11'")} == {("luz-202611", "valor"), ("luz-202611", "dispensado")}


def test_mudar_leva_valor_do_mes_e_deixa_pago(con):
    _luz(con)
    _pagar(con, "luz", "2026-10")
    despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-11", valor="1.00")
    despesas.mudar(con, AGORA3, "r", "painel", "luz", {"valor_padrao": "300.00"})
    assert _comp(con, "luz-202611:2026-11")[0] == 100
    assert con.execute("select compromisso from valor_do_mes where tipo='pago'").fetchone()[0] == "luz"
    assert _comp(con, "luz:2026-10")[2] == "pago"


def test_mudar_mes_pago_recusa(con):
    _luz(con)
    _pagar(con, "luz", "2026-10")
    with pytest.raises(ValueError, match="mês já pago"):
        despesas.mudar_mes(con, AGORA3, "r", "painel", "luz", "2026-10", valor="1.00")


def test_encerrar_antes_de_mes_pago_recusa(con):
    _luz(con, desde_sempre=True)
    _pagar(con, "luz", "2026-10")
    with pytest.raises(ValueError, match="já há pagamento em 2026-10"):
        despesas.encerrar(con, AGORA3, "r", "painel", "luz", ultimo_mes="2026-09")
    assert con.execute("select valido_ate from compromisso_linha where id='luz'").fetchone()[0] is None
    assert despesas.encerrar(con, AGORA3, "r", "painel", "luz")["ultimo_mes"] == "2026-10"


def test_encerrar_padrao_nao_fica_antes_de_pago_adiantado(con):
    _luz(con, desde_sempre=True)
    _pagar(con, "luz", "2026-11")  # novembro pago adiantado, outubro não
    assert despesas.excluir(con, AGORA3, "r", "painel", "luz") == {"id": "luz", "excluida": False, "encerrada": True, "ultimo_mes": "2026-11"}
    assert _comp(con, "luz:2026-11")[2] == "pago" and _comp(con, "luz:2026-10")[2] != "pago"


def test_excluir_com_pago_em_versao_antiga_excluida_encerra(con):
    _luz(con)
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valido_ate, excluido_em) values ('luz-202601','Luz','Luz','dia:10','2026-09','2026-10-01')")
    con.execute("update compromisso_linha set id='luz-202610' where id='luz'")
    con.execute("insert into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, estado) "
                "values ('luz-202601:2026-08','planilha','luz-202601','Luz','2026-08-10','2026-08-10','pago')")
    assert despesas.excluir(con, AGORA3, "r", "painel", "luz")["encerrada"] is True


def test_excluir_com_vinculo_a_conferir_encerra(con):
    _luz(con, desde_sempre=True)
    _ocorrencia(con, "luz:2026-08", "a_conferir")
    con.execute("insert into conciliacao(tx_id, compromisso_id, metodo) values ('tx-1','luz:2026-08','valor')")
    r = despesas.excluir(con, AGORA3, "r", "painel", "luz")
    assert r["encerrada"] is True and _comp(con, "luz:2026-08") is not None


def test_excluir_com_baixa_sem_ocorrencia_encerra(con):
    _luz(con, desde_sempre=True)
    con.execute("insert into valor_do_mes(mes, compromisso, tipo, valor_centavos) values ('2026-08','luz','pago',20000)")
    assert despesas.excluir(con, AGORA3, "r", "painel", "luz")["encerrada"] is True


def test_virada_de_ano(con):
    dez = dt.datetime(2026, 12, 15, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    despesas.criar_fixa(con, dez, "r", "painel", {"nome": "Luz", "valor_padrao": "200.00", "vencimento": "dia:10"})
    con.execute("insert into valor_do_mes(mes, compromisso, tipo, valor_centavos) values ('2026-12','luz','pago',20000)")
    cp.atualizar_compromissos(con, dez.date(), dez)
    assert despesas.mes_inicial(con, "luz", dez.date()) == "2027-01"
    assert despesas.encerrar(con, dez, "r", "painel", "luz")["ultimo_mes"] == "2026-12"
    assert _comp(con, "luz:2027-01") is None and _comp(con, "luz:2026-12")[2] == "pago"
