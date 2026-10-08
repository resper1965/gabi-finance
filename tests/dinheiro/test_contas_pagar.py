import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.contas_pagar import atualizar_compromissos, caixa_unico, contas_a_pagar, marcar_paga_manual
from tests.dinheiro.test_pipeline_compromissos import CASOS, carregar_cenario

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 8)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _comp(con, id_, nome, vu, estado, valor=10000, forma="boleto", fonte="padrao", motivo=None, **dados):
    con.execute("insert into compromisso(id, origem, linha_id, nome, vencimento, vencimento_util, valor_centavos, valor_fonte, forma, estado, motivo, dados) "
                "values (?,?,?,?,?,?,?,?,?,?,?,?)", (id_, "planilha", id_.split(":")[0], nome, vu, vu, valor, fonte, forma, estado, motivo, json.dumps(dados)))


@pytest.fixture
def agenda(con):
    _comp(con, "iptu:2026-10", "IPTU", "2026-10-01", "atrasado", 50000)
    _comp(con, "luz:2026-09", "Luz antiga", "2026-09-20", "atrasado", 20000)
    _comp(con, "condominio:2026-10", "Condomínio", "2026-10-08", "aberto", 80000)
    _comp(con, "energia:2026-10", "Energia", "2026-10-15", "aberto", 23050, fonte="valores_do_mes")
    _comp(con, "agua:2026-10", "Água", "2026-10-09", "previsto", 9000)
    _comp(con, "cartao:2026-10", "Cartão", "2026-10-20", "previsto", 80025, forma="fatura")
    _comp(con, "escola:2026-11", "Escola", "2026-11-06", "previsto", 300000)
    _comp(con, "netflix:2026-10", "Netflix", "2026-10-10", "debito_automatico", 5590, forma="debito_automatico")
    _comp(con, "mensal:2026-10", "Mensalidade", "2026-10-07", "a_conferir", 150000, motivo="pago a menor: R$ 1.500,00 de R$ 3.000,00")
    _comp(con, "aluguel:2026-10", "Aluguel", "2026-10-05", "pago", 200000, forma="pix",
          metodo="favorecido", tx_id="t1", pago_em="2026-10-05", diferenca=0.0)
    return con


def _ids(lista):
    return [i["id"] for i in lista]


def test_grupos_e_ordem(agenda):
    r = contas_a_pagar(agenda, HOJE)
    assert _ids(r["atrasadas"]) == ["luz:2026-09", "iptu:2026-10"]            # mais antiga primeiro
    assert _ids(r["hoje"]) == ["condominio:2026-10"]
    assert _ids(r["proximas"]) == ["agua:2026-10", "energia:2026-10"]          # amanhã até hoje+7
    assert _ids(r["adiante"]) == ["cartao:2026-10", "escola:2026-11"]
    assert _ids(r["debito_automatico"]) == ["netflix:2026-10"]
    assert _ids(r["a_conferir"]) == ["mensal:2026-10"]
    assert _ids(r["pagas"]) == ["aluguel:2026-10"]


def test_atrasadas_trazem_dias_de_atraso(agenda):
    a = {i["id"]: i["dias_atraso"] for i in contas_a_pagar(agenda, HOJE)["atrasadas"]}
    assert a == {"luz:2026-09": 18, "iptu:2026-10": 7}


def test_item_tem_valor_em_centavos_e_origem_do_valor(agenda):
    e = next(i for i in contas_a_pagar(agenda, HOJE)["proximas"] if i["id"] == "energia:2026-10")
    assert e["valor_centavos"] == 23050 and e["valor_fonte"] == "valores_do_mes" and e["vencimento_util"] == "2026-10-15"
    assert isinstance(e["valor_centavos"], int)


def test_paga_mostra_a_conciliacao_com_o_extrato(agenda):
    p = contas_a_pagar(agenda, HOJE)["pagas"][0]
    assert (p["metodo"], p["tx_id"], p["pago_em"], p["diferenca_centavos"]) == ("favorecido", "t1", "2026-10-05", 0)


def test_a_conferir_traz_o_motivo(agenda):
    assert "pago a menor" in contas_a_pagar(agenda, HOJE)["a_conferir"][0]["motivo"]


def test_ate_corta_o_que_vem_depois_mas_nunca_as_atrasadas(agenda):
    r = contas_a_pagar(agenda, HOJE, ate=dt.date(2026, 10, 12))
    assert _ids(r["proximas"]) == ["agua:2026-10"] and r["adiante"] == []
    assert _ids(r["atrasadas"]) == ["luz:2026-09", "iptu:2026-10"]


def test_agenda_vazia(con):
    r = contas_a_pagar(con, HOJE)
    assert all(r[k] == [] for k in ("atrasadas", "hoje", "proximas", "adiante", "debito_automatico", "a_conferir", "pagas"))


# ---------------- caixa único ----------------
def _conta(con, ext, tipo="BANK", estado="sim", apelido=None):
    con.execute("insert into conta(externo_id, instituicao, tipo, apelido, estado) values (?,?,?,?,?)", (ext, "Banco", tipo, apelido or ext, estado))
    return con.execute("select id from conta where externo_id=?", (ext,)).fetchone()[0]


def _saldo(con, cid, em, c):
    con.execute("insert into saldo(conta_id, em, saldo_centavos) values (?,?,?)", (cid, em, c))


def test_caixa_unico_soma_so_contas_liberadas_pelo_ricardo(con):
    a, b, c_, d = _conta(con, "c6", apelido="C6 PJ"), _conta(con, "itau", apelido="Itaú PF"), _conta(con, "fora", estado="nao"), _conta(con, "nova", estado="a_decidir")
    for cid, v in ((a, 100000), (b, 50000), (c_, 999999), (d, 888888)):
        _saldo(con, cid, "2026-10-08T07:00:00", v)
    r = caixa_unico(con, HOJE)
    assert r.saldo_centavos == 150000
    assert sorted(x["apelido"] for x in r.contas) == ["C6 PJ", "Itaú PF"]


def test_caixa_unico_usa_o_saldo_mais_recente_ate_a_data(con):
    a = _conta(con, "c6")
    _saldo(con, a, "2026-10-07T23:00:00", 100000)
    _saldo(con, a, "2026-10-08T15:00:00", 90000)
    _saldo(con, a, "2026-10-09T08:00:00", 1)          # depois da data pedida: ignorado
    assert caixa_unico(con, HOJE).saldo_centavos == 90000
    assert caixa_unico(con, dt.date(2026, 10, 7)).saldo_centavos == 100000


def test_caixa_unico_nao_inclui_cartao_no_saldo_e_soma_faturas_abertas(con):
    b = _conta(con, "c6")
    cc = _conta(con, "cartao", tipo="CREDIT")
    _saldo(con, b, "2026-10-08T07:00:00", 100000)
    _saldo(con, cc, "2026-10-08T07:00:00", -70000)
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f1','cartao','2026-10-20',80025,'OPEN',?)", (cc,))
    con.execute("insert into fatura(id, account_id, vencimento, total_centavos, pagamento_status, conta_id) values ('f0','cartao','2026-09-20',50000,'PAID',?)", (cc,))
    r = caixa_unico(con, HOJE)
    assert r.saldo_centavos == 100000 and r.faturas_abertas_centavos == 80025


def test_caixa_unico_sem_contas(con):
    r = caixa_unico(con, HOJE)
    assert (r.saldo_centavos, r.contas, r.faturas_abertas_centavos) == (0, [], 0)


# ---------------- baixa manual ----------------
def _base(con, nome="base"):
    e = next(c for c in CASOS if c["args"][0] == nome)["saida"]["entrada"]
    carregar_cenario(con, e)
    return e, dt.date.fromisoformat(e["hoje"]), dt.datetime.fromisoformat(e["agora"])


def test_marcar_paga_manual_vira_pago_na_proxima_rodada(con):
    e, h, a = _base(con)
    atualizar_compromissos(con, h, a, docs=e["docs"])
    assert con.execute("select estado from compromisso where id='iptu:2026-10'").fetchone()[0] == "atrasado"
    marcar_paga_manual(con, "iptu:2026-10", por="boss@x.com", hoje=h)
    atualizar_compromissos(con, h, a, docs=e["docs"])
    r = con.execute("select estado, dados from compromisso where id='iptu:2026-10'").fetchone()
    assert r["estado"] == "pago" and json.loads(r["dados"])["metodo"] == "manual"
    d = con.execute("select quem, o_que from decisao order by id desc limit 1").fetchone()
    assert d["quem"] == "boss@x.com" and "iptu:2026-10" in d["o_que"]


def test_marcar_paga_manual_duas_vezes_nao_duplica(con):
    e, h, a = _base(con)
    atualizar_compromissos(con, h, a, docs=e["docs"])
    marcar_paga_manual(con, "iptu:2026-10", por="x", hoje=h)
    marcar_paga_manual(con, "iptu:2026-10", por="x", hoje=h)
    assert con.execute("select count(*) from valor_do_mes where tipo='pago' and compromisso='iptu'").fetchone()[0] == 1


def test_marcar_paga_manual_id_inexistente(con):
    with pytest.raises(LookupError):
        marcar_paga_manual(con, "nada:2026-10", por="x", hoje=HOJE)


def test_marcar_paga_manual_so_para_compromisso_de_linha(con):
    _comp(con, "fatura:c9999:2026-10", "Fatura", "2026-10-20", "aberto")
    con.execute("update compromisso set linha_id=NULL where id='fatura:c9999:2026-10'")
    with pytest.raises(ValueError):
        marcar_paga_manual(con, "fatura:c9999:2026-10", por="x", hoje=HOJE)


def test_valor_criado_no_painel_sem_numero_de_linha_nao_quebra_e_vence_o_antigo(con):
    e, h, a = _base(con)
    # a planilha já traz R$ 230,50 para a energia; o Ricardo corrige no painel (linha criada sem número de planilha)
    con.execute("insert into valor_do_mes(mes, compromisso, tipo, valor_centavos, origem) values ('2026-10','energia','valor',24000,'painel')")
    atualizar_compromissos(con, h, a, docs=[])
    r = con.execute("select valor_centavos, valor_fonte from compromisso where id='energia:2026-10'").fetchone()
    assert (r["valor_centavos"], r["valor_fonte"]) == (24000, "valores_do_mes")


def test_linha_criada_no_painel_sem_numero_entra_depois_das_da_planilha(con):
    e, h, a = _base(con)
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento, valor_tipo, valor_padrao_centavos) values ('novo','Novo','NOVO LTDA','dia:20','fixo',12345)")
    leitura = __import__("gabi.dinheiro.repositorio", fromlist=["x"]).ler_leitura(con)
    assert leitura["linhas"][-1]["id"] == "novo" and isinstance(leitura["linhas"][-1]["linha_planilha"], int)
    atualizar_compromissos(con, h, a, docs=[])
    assert con.execute("select valor_centavos from compromisso where id='novo:2026-10'").fetchone()[0] == 12345
