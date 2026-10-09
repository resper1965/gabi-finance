import datetime as dt
import fcntl
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gabi.db import conectar, migrar
from gabi.dinheiro.captura import capturar_saldos
from gabi.dinheiro.rodar import RodadaEmAndamento, rodar_extratos, rodar_saldos
from tests.dinheiro.test_captura import AGORA, BANCO, CARTAO, HOJE, FakeFin, tx

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    return c


def _liberada(con):
    """Só conta liberada (estado 'sim') conta para a rodada conferida; a captura preserva o estado ao atualizar."""
    con.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('acc-bank-1111','Banco','BANK','sim')")


def _boa_historia(n_dias=30):
    """Movimento em todo dia útil dos últimos dias: conferências de buraco/volume passam."""
    txs, d, i = [], HOJE - dt.timedelta(days=n_dias), 0
    while d < HOJE:
        if d.weekday() < 5:
            i += 1
            txs.append(tx(f"t{i}", d.isoformat(), f"LOJA {i}", 10.0 + i))
        d += dt.timedelta(days=1)
    return {"acc-bank-1111": txs}


def _rodar_ext(con, fin, tmp_path, **kw):
    return rodar_extratos(con, fin, HOJE, AGORA, tmp_path / "bruto", tmp_path / "locks", **kw)


# ---------------- extratos: captura + conferência + classificação + compromissos ----------------
def test_extratos_encadeia_captura_conferencia_classificacao_e_compromissos(con, tmp_path):
    _liberada(con)
    con.execute("insert into categoria(nome) values ('Compras')")
    r = _rodar_ext(con, FakeFin([BANCO], _boa_historia()), tmp_path)
    assert r.captura.lidos > 10 and r.captura.falhas == []
    assert con.execute("select count(*) from conferencia where rodada_id=?", (r.captura.rodada_id,)).fetchone()[0] == 3  # 1 conta x 3 conferências
    assert r.conferida is True and con.execute("select conferida from rodada where id=?", (r.captura.rodada_id,)).fetchone()[0] == 1
    assert r.compromissos.gerados == 0  # sem Cadastros de compromissos ainda: roda sem quebrar


def test_rodada_com_saldo_incoerente_nao_e_conferida_e_dados_ate_nao_avanca(con, tmp_path):
    _liberada(con)
    from gabi.envelope import envelope
    fin = FakeFin([BANCO], _boa_historia())
    r1 = _rodar_ext(con, fin, tmp_path)
    assert r1.conferida is True
    # no dia seguinte o saldo despenca sem lançamento que o explique
    fin2 = FakeFin([{**BANCO, "balance": 1.0}], _boa_historia())
    r2 = rodar_extratos(con, fin2, HOJE + dt.timedelta(days=1), AGORA + dt.timedelta(days=1), tmp_path / "bruto", tmp_path / "locks")
    assert r2.conferida is False
    e = envelope(con, {}, agora=(AGORA + dt.timedelta(days=1)).astimezone(dt.timezone.utc))
    assert e["fontes"][0]["estado"] == "nao_conferida" and e["dados_ate"] == envelope(con, {}, agora=AGORA.astimezone(dt.timezone.utc))["dados_ate"]


def test_conta_que_falhou_impede_a_conferencia(con, tmp_path):
    r = _rodar_ext(con, FakeFin([BANCO, CARTAO], _boa_historia(), falha={"acc-card-9999"}), tmp_path)
    assert r.captura.falhas == ["acc-card-9999"] and r.conferida is False


def test_so_confere_contas_liberadas_ou_todas_as_bank(con, tmp_path):
    r = _rodar_ext(con, FakeFin([BANCO, CARTAO], _boa_historia()), tmp_path)
    tipos = {x["conta"] for x in con.execute("select c.externo_id as conta from conferencia f join conta c on c.id=f.conta_id")}
    assert tipos == {"acc-bank-1111", "acc-card-9999"}  # cartão também é conferido (volume e buracos), saldo do cartão é dispensado


def test_extratos_classifica_o_que_ficou_sem_categoria(con, tmp_path):
    con.execute("insert into categoria(nome) values ('Compras')")
    con.execute("insert into regra(padrao, acao, ativa, criado_em) values ('LOJA', '{\"categoria_id\": 1}', 1, '2026-10-08')")
    _rodar_ext(con, FakeFin([BANCO], _boa_historia()), tmp_path)
    assert con.execute("select count(*) from lancamento where categoria_id is null").fetchone()[0] == 0


def test_extratos_atualiza_compromissos_do_cadastro(con, tmp_path):
    from gabi.dinheiro import repositorio
    repositorio.gravar_leitura(con, {"linhas": [{"id": "aluguel", "nome": "Aluguel", "extrato": "LOJA 5", "apelidos": [], "vencimento": "dia:5",
                                                  "ajuste_dia_util": "adia", "valor_tipo": "fixo", "valor_padrao": 15.0, "forma": "pix", "conta": "",
                                                  "cartao": "", "documento": "", "pix": "", "ativo": True, "valido_de": None, "valido_ate": None,
                                                  "linha_planilha": 2}], "params": {}, "valores": []})
    r = _rodar_ext(con, FakeFin([BANCO], _boa_historia()), tmp_path)
    assert r.compromissos.gerados >= 2 and con.execute("select count(*) from compromisso where id like 'aluguel:%'").fetchone()[0] >= 2


def test_extratos_pode_sincronizar_antes(con, tmp_path):
    fin = FakeFin([BANCO], _boa_historia())
    chamadas = []
    original = fin.__call__

    def espiao(ferramenta, args, tent=5):
        chamadas.append(ferramenta)
        if ferramenta in ("openfinance_list_connections", "openfinance_force_sync", "openfinance_get_item_status"):
            return {"connections": []} if ferramenta == "openfinance_list_connections" else {}
        return original(ferramenta, args, tent)

    _rodar_ext(con, espiao, tmp_path, sincronizar_antes=True)
    assert chamadas[0] == "openfinance_list_connections"


# ---------------- uma rodada por fonte por vez ----------------
def test_rodada_concorrente_e_recusada_pelo_lock(con, tmp_path):
    (tmp_path / "locks").mkdir()
    with open(tmp_path / "locks" / "extratos.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        with pytest.raises(RodadaEmAndamento):
            _rodar_ext(con, FakeFin([BANCO], {}), tmp_path)
    _rodar_ext(con, FakeFin([BANCO], {}), tmp_path / "outro")  # solto o lock, roda


def test_o_lock_e_liberado_mesmo_se_a_rodada_falhar(con, tmp_path):
    class Quebra:
        def __call__(self, *a, **k):
            raise RuntimeError("fonte caiu")

    with pytest.raises(RuntimeError):
        _rodar_ext(con, Quebra(), tmp_path)
    _rodar_ext(con, FakeFin([BANCO], {}), tmp_path)  # não ficou preso


# ---------------- saldos (de hora em hora) ----------------
def test_saldos_so_grava_saldo_sem_ler_extrato(con, tmp_path):
    fin = FakeFin([BANCO, CARTAO], _boa_historia())
    n = rodar_saldos(con, fin, AGORA, tmp_path / "locks")
    assert n == 2
    assert con.execute("select count(*) from lancamento").fetchone()[0] == 0
    assert "openfinance_list_transactions" not in [f for f, _ in fin.pedidos]
    assert con.execute("select saldo_centavos from saldo where conta_id=1").fetchone()[0] == 123456
    assert con.execute("select fonte, status from rodada").fetchone()[:] == ("open-finance-saldos", "ok")


def test_saldos_atualiza_o_saldo_no_estado_da_conta(con, tmp_path):
    rodar_saldos(con, FakeFin([BANCO], {}), AGORA, tmp_path / "locks")
    assert con.execute("select saldo_centavos from conta_estado where account_id='acc-bank-1111'").fetchone()[0] == 123456


def test_saldos_nao_aparece_como_fonte_nem_atrapalha_o_dados_ate(con, tmp_path):
    _liberada(con)
    from gabi.envelope import envelope
    _rodar_ext(con, FakeFin([BANCO], _boa_historia()), tmp_path)
    rodar_saldos(con, FakeFin([BANCO], {}), AGORA + dt.timedelta(hours=1), tmp_path / "locks")
    e = envelope(con, {}, agora=AGORA.astimezone(dt.timezone.utc))
    assert [f["nome"] for f in e["fontes"]] == ["open-finance"] and e["desatualizado"] is False


def test_saldos_preserva_estado_da_conta_e_apelido(con, tmp_path):
    rodar_saldos(con, FakeFin([BANCO], {}), AGORA, tmp_path / "locks")
    con.execute("update conta set estado='sim', apelido='C6 PJ' where externo_id='acc-bank-1111'")
    rodar_saldos(con, FakeFin([BANCO], {}), AGORA + dt.timedelta(hours=1), tmp_path / "locks")
    assert con.execute("select estado, apelido from conta").fetchone()[:] == ("sim", "C6 PJ")


def test_saldos_com_erro_registra_rodada_erro_e_relevanta(con, tmp_path):
    class Quebra:
        def __call__(self, *a, **k):
            raise RuntimeError("sem rede")

    with pytest.raises(RuntimeError):
        rodar_saldos(con, Quebra(), AGORA, tmp_path / "locks")
    assert con.execute("select status from rodada").fetchone()[0] == "erro"


def test_extratos_propoe_recebimento_de_nota_para_credito_em_conta_do_caixa_unico(con, tmp_path):
    _liberada(con)
    con.execute("insert into nota_fiscal(id, numero, emissao, status, valor_bruto_centavos, tomador_nome, vencimento, valor_liquido_centavos, importado_em, atualizado_em) "
                "values ('n1','7','2026-09-20','autorizada',110000,'CLIENTE X','2026-10-08',100000,'x','x')")
    historia = _boa_historia()
    historia["acc-bank-1111"].append(tx("cred1", (HOJE - dt.timedelta(days=1)).isoformat(), "Pix recebido CLIENTE X", 1000.0, tipo="CREDIT"))
    _rodar_ext(con, FakeFin([BANCO], historia), tmp_path)        # bancos_pj vazio: a conta é do caixa único e é suficiente
    assert con.execute("select nota_id, estado from recebimento_nota").fetchall()[0][:] == ("n1", "proposto")
