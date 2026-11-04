import datetime as dt
import gzip
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro import captura
from gabi.dinheiro.captura import capturar, hora_de_sincronizar, janela_inicio, sincronizar

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
HOJE = dt.date(2026, 10, 8)
AGORA = dt.datetime(2026, 10, 8, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

BANCO = {"account_id": "acc-bank-1111", "type": "BANK", "name": "Conta C6", "bank": "C6 Bank", "balance": 1234.56, "owner": "Ricardo Teste"}
CARTAO = {"account_id": "acc-card-9999", "type": "CREDIT", "name": "Cartao Itau", "bank": "Itau", "balance": -800.0, "owner": "Ricardo Teste",
          "creditData": {"creditLimit": 5000, "availableCreditLimit": 4200.5, "balanceDueDate": "2026-10-20"}}


def tx(i, data, desc, valor, tipo="DEBIT", **extra):
    return {"id": i, "date": f"{data}T00:00:00Z", "description": desc, "amount": valor, "type": tipo, **extra}


class FakeFin:
    """Faz o papel do cliente da mcp.ai: devolve respostas prontas e anota o que foi pedido."""

    def __init__(self, contas, txs, faturas=None, por_pagina=500, falha=()):
        self.contas, self.txs, self.faturas = contas, txs, faturas or {}
        self.por_pagina, self.falha, self.pedidos = por_pagina, set(falha), []

    def __call__(self, ferramenta, args, tent=5):
        self.pedidos.append((ferramenta, args))
        if ferramenta == "openfinance_list_accounts":
            return {"results": self.contas}
        if ferramenta == "openfinance_list_transactions":
            aid = args["account_id"]
            if aid in self.falha:
                raise ConnectionError("sem resposta")
            itens, p, n = self.txs.get(aid, []), args["page"], self.por_pagina
            return {"results": itens[(p - 1) * n:p * n], "totalPages": max(1, -(-len(itens) // n))}
        if ferramenta == "openfinance_list_credit_card_bills":
            return {"bills": self.faturas.get(args["account_id"], [])}
        raise AssertionError(ferramenta)


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _rodar(con, fin, tmp_path, **kw):
    return capturar(con, fin, HOJE, AGORA, tmp_path / "bruto", **kw)


def _lancs(con):
    return {r["externo_id"]: r for r in con.execute("select * from lancamento")}


def test_cria_contas_a_decidir_com_saldo_e_limites_em_centavos(con, tmp_path):
    _rodar(con, FakeFin([BANCO, CARTAO], {}), tmp_path)
    c = {r["externo_id"]: r for r in con.execute("select * from conta")}
    assert c["acc-bank-1111"]["estado"] == "a_decidir" and c["acc-bank-1111"]["instituicao"] == "C6 Bank"
    assert c["acc-card-9999"]["limite_centavos"] == 500000 and c["acc-card-9999"]["disponivel_centavos"] == 420050
    assert c["acc-card-9999"]["vencimento_fatura"] == "2026-10-20" and c["acc-bank-1111"]["titular"] == "Ricardo Teste"
    assert con.execute("select saldo_centavos from saldo where conta_id=?", (c["acc-bank-1111"]["id"],)).fetchone()[0] == 123456
    e = con.execute("select saldo_centavos, banco from conta_estado where account_id='acc-bank-1111'").fetchone()
    assert (e["saldo_centavos"], e["banco"]) == (123456, "C6 Bank")


def test_valores_sinal_e_natureza(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA BOM PAO", 35.5, paymentData={"paymentMethod": "PIX"}, operationType="PIX"),
                              tx("t2", "2026-10-01", "SALARIO", 8000.0, tipo="CREDIT"),
                              tx("t3", "2026-10-02", "PAGAMENTO FATURA CARTAO", -300.0)]}
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    L = _lancs(con)
    assert L["t1"]["valor_centavos"] == -3550 and L["t1"]["natureza"] == "caixa+custo" and L["t1"]["forma"] == "PIX"
    assert L["t1"]["operacao"] == "PIX" and L["t1"]["data"] == "2026-10-07" and L["t1"]["status"] == "posted"
    assert L["t2"]["valor_centavos"] == 800000 and L["t2"]["natureza"] == "caixa"
    assert L["t3"]["natureza"] == "caixa"  # paga fatura: só caixa
    assert con.execute("select typeof(valor_centavos) from lancamento limit 1").fetchone()[0] == "integer"


def test_cartao_parcelas_fatura_e_estorno(con, tmp_path):
    meta = {"creditCardMetadata": {"installmentNumber": 2, "totalInstallments": 5, "purchaseDate": "2026-08-03T00:00:00Z", "billId": "bill1"}}
    txs = {"acc-card-9999": [tx("c1", "2026-10-03", "MERCADO", 310.0, **meta), tx("c2", "2026-10-04", "ESTORNO LOJA", 20.0, tipo="CREDIT")]}
    faturas = {"acc-card-9999": [{"id": "bill1", "dueDate": "2026-10-20T00:00:00Z", "totalAmount": 800.25, "minimumPaymentAmount": 80.0}]}
    _rodar(con, FakeFin([CARTAO], txs, faturas), tmp_path)
    L = _lancs(con)
    assert (L["c1"]["valor_centavos"], L["c1"]["parcela"], L["c1"]["parcelas"], L["c1"]["fatura_id"], L["c1"]["data_compra"]) == (
        -31000, 2, 5, "bill1", "2026-08-03")
    assert L["c1"]["natureza"] == "custo" and L["c2"]["valor_centavos"] == 2000
    f = con.execute("select * from fatura").fetchone()
    assert (f["id"], f["vencimento"], f["total_centavos"], f["minimo_centavos"], f["account_id"]) == ("bill1", "2026-10-20", 80025, 8000, "acc-card-9999")
    assert f["conta_id"] is not None


def test_captura_idempotente(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5), tx("t2", "2026-10-01", "SALARIO", 8000.0, tipo="CREDIT")]}
    fin = FakeFin([BANCO], txs)
    r1 = _rodar(con, fin, tmp_path)
    antes = [tuple(r) for r in con.execute("select * from lancamento order by id")]
    r2 = capturar(con, fin, HOJE, AGORA + dt.timedelta(hours=1), tmp_path / "bruto")
    assert (r1.novos, r2.novos) == (2, 0) and r2.lidos == 2
    assert [tuple(r) for r in con.execute("select * from lancamento order by id")] == antes


def test_dado_do_futuro_nao_e_lancamento_e_o_antigo_e_removido(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5), tx("fut", "2026-10-20", "PARCELA FUTURA", 50.0)]}
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    assert set(_lancs(con)) == {"t1"}
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos) values (1, 'velho-futuro', '2026-12-01', 1)")
    con.execute("insert into conciliacao(tx_id, compromisso_id) values ('velho-futuro', 7)")
    capturar(con, FakeFin([BANCO], txs), HOJE, AGORA + dt.timedelta(minutes=1), tmp_path / "bruto")
    assert "velho-futuro" not in _lancs(con)
    assert con.execute("select count(*) from conciliacao where tx_id='velho-futuro'").fetchone()[0] == 0


def test_nunca_sobrescreve_a_decisao_do_ricardo(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA BOM PAO", 35.5)]}
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    con.execute("insert into categoria(nome) values ('Mercado')")
    con.execute("insert into pessoa(id, nome) values ('p1','Ana')")
    con.execute("update lancamento set categoria_id=1, categoria_origem='voce', para_quem_id='p1', para_quem_origem='voce' where externo_id='t1'")
    txs["acc-bank-1111"][0]["description"] = "PADARIA BOM PAO LTDA"  # a fonte mudou a descrição
    capturar(con, FakeFin([BANCO], txs), HOJE, AGORA + dt.timedelta(hours=1), tmp_path / "bruto")
    r = _lancs(con)["t1"]
    assert (r["categoria_id"], r["categoria_origem"], r["para_quem_id"], r["para_quem_origem"]) == (1, "voce", "p1", "voce")
    assert r["descricao_original"] == "PADARIA BOM PAO LTDA"  # o dado da fonte é atualizado


def test_conta_que_o_ricardo_liberou_continua_liberada(con, tmp_path):
    fin = FakeFin([BANCO], {})
    _rodar(con, fin, tmp_path)
    con.execute("update conta set estado='sim', apelido='C6 PJ' where externo_id='acc-bank-1111'")
    capturar(con, fin, HOJE, AGORA + dt.timedelta(hours=1), tmp_path / "bruto")
    r = con.execute("select estado, apelido from conta").fetchone()
    assert (r["estado"], r["apelido"]) == ("sim", "C6 PJ")


def test_paginacao_ate_totalPages(con, tmp_path):
    txs = {"acc-bank-1111": [tx(f"t{i}", "2026-10-07", f"LOJA {i}", 10.0 + i) for i in range(5)]}
    fin = FakeFin([BANCO], txs, por_pagina=2)
    r = _rodar(con, fin, tmp_path)
    assert r.lidos == 5 and len(_lancs(con)) == 5
    paginas = [a["page"] for f, a in fin.pedidos if f == "openfinance_list_transactions"]
    assert paginas == [1, 2, 3]


def test_janela_inicio_e_ultimo_dia_real_menos_10(con, tmp_path):
    fin = FakeFin([BANCO], {"acc-bank-1111": [tx("t1", "2026-10-05", "X", 1.0), tx("fut", "2026-12-01", "Y", 1.0)]})
    _rodar(con, fin, tmp_path)
    cid = con.execute("select id from conta").fetchone()[0]
    assert janela_inicio(con, cid, HOJE) == "2026-09-25"  # 05/10 menos 10 dias; o futuro não conta
    segunda = FakeFin([BANCO], {})
    _rodar(con, segunda, tmp_path / "x")
    assert [a["from"] for f, a in segunda.pedidos if f == "openfinance_list_transactions"] == ["2026-09-25"]


def test_janela_sem_historico_e_400_dias(con, tmp_path):
    _rodar(con, FakeFin([BANCO], {}), tmp_path)
    cid = con.execute("select id from conta").fetchone()[0]
    assert janela_inicio(con, cid, HOJE) == (HOJE - dt.timedelta(days=400)).isoformat()


def test_unificar_pending_posted_substitui_pending_e_leva_o_vinculo(con, tmp_path):
    txs = {"acc-bank-1111": [tx("p1", "2026-10-06", "PADARIA BOM PAO", 35.5, status="PENDING")]}
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    assert _lancs(con)["p1"]["status"] == "pending"
    con.execute("insert into conciliacao(tx_id, compromisso_id) values ('p1', 3)")
    txs["acc-bank-1111"] = [tx("q1", "2026-10-07", "PADARIA BOM PAO LTDA", 35.5, status="POSTED")]
    capturar(con, FakeFin([BANCO], txs), HOJE, AGORA + dt.timedelta(hours=1), tmp_path / "bruto")
    assert set(_lancs(con)) == {"q1"}
    assert con.execute("select tx_id from conciliacao where compromisso_id=3").fetchone()[0] == "q1"


def test_unificar_pending_so_com_mesmo_valor_e_ate_3_dias(con, tmp_path):
    txs = {"acc-bank-1111": [tx("p1", "2026-10-01", "PADARIA", 35.5, status="PENDING"),
                              tx("p2", "2026-10-06", "FARMACIA SAUDE", 10.0, status="PENDING"),
                              tx("q1", "2026-10-07", "PADARIA", 35.5, status="POSTED"),   # 6 dias: não casa com p1
                              tx("q2", "2026-10-07", "FARMACIA SAUDE", 11.0, status="POSTED")]}  # valor diferente
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    assert set(_lancs(con)) == {"p1", "p2", "q1", "q2"}


def test_falha_numa_conta_nao_derruba_as_outras_e_vira_erro_de_leitura(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5)], "acc-card-9999": [tx("c1", "2026-10-03", "MERCADO", 10.0)]}
    r = _rodar(con, FakeFin([BANCO, CARTAO], txs, falha={"acc-bank-1111"}), tmp_path)
    assert r.falhas == ["acc-bank-1111"] and set(_lancs(con)) == {"c1"}
    est = {x["account_id"]: x["status_conexao"] for x in con.execute("select * from conta_estado")}
    assert est["acc-bank-1111"].startswith("ERRO_LEITURA") and not est["acc-card-9999"].startswith("ERRO_LEITURA")
    rod = con.execute("select status, erro from rodada").fetchone()
    assert rod["status"] == "ok" and "acc-bank-1111" in rod["erro"]  # rodada parcial fica visível


def test_bruto_e_gravado_antes_do_processamento(con, tmp_path, monkeypatch):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5)]}
    monkeypatch.setattr(captura.caixa, "natureza", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("explodiu no processamento")))
    r = _rodar(con, FakeFin([BANCO], txs), tmp_path)
    assert r.falhas == ["acc-bank-1111"]
    arqs = list((tmp_path / "bruto").rglob("*.jsonl.gz"))
    assert arqs and any("PADARIA" in gzip.open(a, "rt", encoding="utf-8").read() for a in arqs)


def test_bruto_nao_contem_a_chave_nem_segredos(con, tmp_path):
    _rodar(con, FakeFin([BANCO], {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5)]}), tmp_path)
    for a in (tmp_path / "bruto").rglob("*.jsonl.gz"):
        assert "sk_live" not in gzip.open(a, "rt", encoding="utf-8").read()


def test_rodada_registrada_com_lidos_e_novos(con, tmp_path):
    _rodar(con, FakeFin([BANCO], {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5)]}), tmp_path)
    r = con.execute("select fonte, status, lidos, novos from rodada").fetchone()
    assert tuple(r) == ("open-finance", "ok", 1, 1)


def test_banco_pj_marca_a_conta(con, tmp_path):
    _rodar(con, FakeFin([BANCO, CARTAO], {}), tmp_path, bancos_pj={"C6 Bank"})
    assert {r["externo_id"]: r["pj"] for r in con.execute("select externo_id, pj from conta")} == {"acc-bank-1111": 1, "acc-card-9999": 0}
    assert {r["account_id"]: r["pj"] for r in con.execute("select account_id, pj from conta_estado")}["acc-bank-1111"] == 1


# ---------------- sincronização forçada ----------------
class FakeSync:
    def __init__(self, status_por_chamada):
        self.status, self.n, self.pedidos = status_por_chamada, 0, []

    def __call__(self, ferramenta, args, tent=5):
        self.pedidos.append(ferramenta)
        if ferramenta == "openfinance_list_connections":
            return {"connections": [{"item_id": "i1", "connector_name": "C6 Bank"}, {"item_id": "i2", "connector_name": "Itau"}]}
        if ferramenta == "openfinance_force_sync":
            return {}
        i = min(self.n, len(self.status) - 1)
        self.n += 1
        return {"items": self.status[i]}


def test_sincronizar_espera_ate_lastUpdatedAt_depois_do_pedido():
    ini = "2026-10-08T10:00:00"
    antes = [{"id": "i1", "status": "UPDATED", "lastUpdatedAt": "2026-10-08T09:00:00Z"}, {"id": "i2", "status": "UPDATED", "lastUpdatedAt": "2026-10-08T09:00:00Z"}]
    depois = [{"id": "i1", "status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": "2026-10-08T10:01:00Z"},
              {"id": "i2", "status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": "2026-10-08T10:02:00Z"}]
    esperas = []
    estados, problemas = sincronizar(FakeSync([antes, depois]), dorme=esperas.append, inicio=ini)
    assert estados == {"C6 Bank": "SUCCESS", "Itau": "SUCCESS"} and problemas == {} and esperas == [30]


def test_sincronizar_reporta_erro_de_login_e_timeout():
    ini = "2026-10-08T10:00:00"
    estado = [{"id": "i1", "status": "LOGIN_ERROR", "lastUpdatedAt": "2026-10-08T09:00:00Z"},
              {"id": "i2", "status": "UPDATED", "lastUpdatedAt": "2026-10-08T09:00:00Z"}]
    relogio = iter(range(0, 10000, 100))
    estados, problemas = sincronizar(FakeSync([estado]), dorme=lambda s: None, agora=lambda: next(relogio), limite=250, inicio=ini)
    assert problemas["C6 Bank"] == "LOGIN_ERROR" and "não atualizou em 4 min" in problemas["Itau"]


def test_hora_de_sincronizar():
    assert hora_de_sincronizar("7,11,15,19", 15) and not hora_de_sincronizar("7,11,15,19", 8) and not hora_de_sincronizar("", 7)


def test_guarda_a_categoria_do_banco_para_a_equivalencia(con, tmp_path):
    txs = {"acc-bank-1111": [tx("t1", "2026-10-07", "PADARIA", 35.5, category="Groceries"), tx("t2", "2026-10-07", "X", 1.0)]}
    _rodar(con, FakeFin([BANCO], txs), tmp_path)
    L = _lancs(con)
    assert L["t1"]["categoria_banco"] == "Groceries" and L["t2"]["categoria_banco"] is None


# ---------------- EV2: rodada interrompida retoma sem refazer contas prontas ----------------
class Cai(FakeFin):
    """Como o FakeFin, mas o processo 'morre' (BaseException) ao pedir o extrato de `morre_em`."""

    def __init__(self, *a, morre_em=None, **k):
        super().__init__(*a, **k)
        self.morre_em = morre_em

    def __call__(self, ferramenta, args, tent=5):
        if ferramenta == "openfinance_list_transactions" and args["account_id"] == self.morre_em:
            self.pedidos.append((ferramenta, args))
            raise KeyboardInterrupt()
        return super().__call__(ferramenta, args, tent)


BANCO2 = {**BANCO, "account_id": "acc-bank-2222", "name": "Conta Itau", "bank": "Itau"}
TXS = {"acc-bank-1111": [tx("a1", "2026-10-07", "PIX A", 10.0)], "acc-bank-2222": [tx("b1", "2026-10-07", "PIX B", 20.0)]}


def _extratos_pedidos(fin):
    return [a["account_id"] for f, a in fin.pedidos if f == "openfinance_list_transactions"]


def test_rodada_interrompida_nao_refaz_a_conta_pronta(con, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        _rodar(con, Cai([BANCO, BANCO2], TXS, morre_em="acc-bank-2222"), tmp_path)
    assert con.execute("select count(*) from lancamento").fetchone()[0] == 1  # a primeira conta ficou gravada
    fin = FakeFin([BANCO, BANCO2], TXS)
    r = _rodar(con, fin, tmp_path)
    assert _extratos_pedidos(fin) == ["acc-bank-2222"]  # a 1111 não foi lida de novo
    assert r.lidos == 2 and r.novos == 2 and con.execute("select count(*) from lancamento").fetchone()[0] == 2
    assert con.execute("select count(*) from rodada where fonte='open-finance' and status='erro'").fetchone()[0] == 1


def test_rodada_ok_anterior_nao_pula_nada(con, tmp_path):
    _rodar(con, FakeFin([BANCO, BANCO2], TXS), tmp_path)
    fin = FakeFin([BANCO, BANCO2], TXS)
    _rodar(con, fin, tmp_path)
    assert sorted(_extratos_pedidos(fin)) == ["acc-bank-1111", "acc-bank-2222"]


def test_checkpoint_de_outro_dia_ou_velho_demais_nao_vale(con, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        _rodar(con, Cai([BANCO, BANCO2], TXS, morre_em="acc-bank-2222"), tmp_path)
    fin = FakeFin([BANCO, BANCO2], TXS)
    capturar(con, fin, HOJE + dt.timedelta(days=1), AGORA + dt.timedelta(days=1), tmp_path / "bruto")  # no dia seguinte
    assert sorted(_extratos_pedidos(fin)) == ["acc-bank-1111", "acc-bank-2222"]


def test_rodada_presa_em_rodando_vira_interrompida(con, tmp_path):
    con.execute("insert into rodada(fonte, inicio, status) values ('open-finance', '2026-10-08T10:00:00+00:00', 'rodando')")
    _rodar(con, FakeFin([BANCO], {}), tmp_path)
    r = con.execute("select status, erro from rodada where id=1").fetchone()
    assert r["status"] == "erro" and r["erro"] == "interrompida"


def test_sincronizar_devolve_a_ultima_atualizacao_de_cada_banco_pelo_nome():
    ini = "2026-10-08T10:00:00"
    st = [{"id": "i1", "status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": "2026-10-08T10:01:00Z"},
          {"id": "i2", "status": "UPDATED", "executionStatus": "SUCCESS", "lastUpdatedAt": "2026-10-07T09:00:00Z"}]
    relogio = iter(range(0, 10000, 100))
    ultimas = {}
    sincronizar(FakeSync([st]), dorme=lambda s: None, agora=lambda: next(relogio), limite=250, inicio=ini, ultimas=ultimas)
    assert ultimas == {"C6 Bank": "2026-10-08T10:01:00Z", "Itau": "2026-10-07T09:00:00Z"}


def test_boleto_da_fatura_sai_de_gastos_na_mesma_rodada_e_a_marcacao_manual_fica(con, tmp_path):
    """O banco vem antes do cartão na lista: o boleto só se confere com a fatura depois de todas as contas gravadas."""
    txs = {"acc-bank-1111": [tx("b1", "2026-10-07", "Pagamento de boleto ITAU UNIBANCO HOLDING S.A.", 800.25, category="Transfer - Bank Slip"),
                              tx("b2", "2026-10-05", "Pagamento de boleto AVENUES SAO PAULO EDUCACAO LTD", 9766.67, category="Transfer - Bank Slip")]}
    faturas = {"acc-card-9999": [{"id": "bill1", "dueDate": "2026-10-10T00:00:00Z", "totalAmount": 800.25}]}
    fin = FakeFin([BANCO, CARTAO], txs, faturas)
    _rodar(con, fin, tmp_path)
    L = _lancs(con)
    assert (L["b1"]["natureza"], L["b1"]["natureza_regra"]) == ("caixa", "fatura")
    assert (L["b2"]["natureza"], L["b2"]["natureza_regra"]) == ("caixa+custo", None)
    con.execute("update lancamento set natureza_manual='nao_gasto' where externo_id='b2'")
    _rodar(con, fin, tmp_path)  # a captura regrava a natureza bruta; a marcação do Ricardo volta a valer
    L = _lancs(con)
    assert (L["b2"]["natureza"], L["b2"]["natureza_regra"]) == ("caixa", "manual")


def test_captura_preenche_gastador_e_mantem_indicacao(con, tmp_path):
    from gabi.dinheiro import gastador
    con.execute("insert into pessoa(id, nome, papel) values ('ricardo','Ricardo','titular'), ('louise','Louise','filha')")
    txs = {"acc-bank-1111": [tx("b1", "2026-10-07", "PADARIA", 10.0)], "acc-card-9999": [tx("c1", "2026-10-03", "ZARA", 310.0)]}
    fin = FakeFin([BANCO, CARTAO], txs)
    _rodar(con, fin, tmp_path)
    L = _lancs(con)
    assert (L["b1"]["gastador_id"], L["b1"]["gastador_origem"]) == ("ricardo", "cartao")
    assert L["c1"]["gastador_id"] is None  # cartão sem portador cadastrado: a indicar
    con.execute("update conta set usuarios='[\"ricardo\",\"louise\"]' where externo_id='acc-card-9999'")
    gastador.indicar(con, [L["c1"]["id"]], "louise")
    _rodar(con, fin, tmp_path)
    L = _lancs(con)
    assert (L["c1"]["gastador_id"], L["c1"]["gastador_origem"]) == ("louise", "voce")


def test_lancamento_ilegivel_nao_sobrescreve_valor(con, tmp_path):
    _rodar(con, FakeFin([BANCO], {"acc-bank-1111": [tx("t1", "2026-10-07", "LOJA", "-50.00")]}), tmp_path)
    fin = FakeFin([BANCO], {"acc-bank-1111": [tx("t1", "2026-10-07", "LOJA", "lixo"), tx("t2", "2026-10-07", "OUTRA", "-10.00")]})
    r = capturar(con, fin, HOJE, AGORA + dt.timedelta(minutes=5), tmp_path / "bruto")
    L = _lancs(con)
    assert L["t1"]["valor_centavos"] == -5000 and L["t2"]["valor_centavos"] == -1000
    assert r.ilegiveis == 1


def test_saldo_ilegivel_nao_grava(con, tmp_path):
    ruim = {**BANCO, "balance": "abc"}
    _rodar(con, FakeFin([ruim, CARTAO], {}), tmp_path)
    n = lambda aid: con.execute("select count(*) from saldo s join conta c on c.id=s.conta_id where c.externo_id=?", (aid,)).fetchone()[0]
    assert n("acc-bank-1111") == 0 and n("acc-card-9999") == 1


def test_purgar_futuro_tudo_ou_nada(con):
    con.execute("insert into conta(id, externo_id) values (1, 'c1')")
    for i, x in enumerate(("f1", "f2"), start=1):
        con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos) values (1, ?, '2026-12-01', 1)", (x,))
        con.execute("insert into conciliacao(tx_id, compromisso_id) values (?, ?)", (x, i))
    con.execute("create trigger falha_f2 before delete on lancamento when old.externo_id='f2' begin select raise(abort, 'falha simulada'); end")
    with pytest.raises(Exception):
        captura._purgar_futuro(con, HOJE)
    assert {r[0] for r in con.execute("select externo_id from lancamento")} == {"f1", "f2"}
    assert con.execute("select count(*) from conciliacao").fetchone()[0] == 2
