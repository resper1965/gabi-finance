import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.avisos import gerar_avisos
from gabi.db import conectar, migrar

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 16, 12, 0, tzinfo=UTC)        # 09:00 em Brasília
MIGR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    c.execute("insert into conta(externo_id, instituicao, tipo, estado) values ('c1','Itau','BANK','sim')")
    return c


def _rodada(con, horas_atras: float, conferida: int, fonte="open-finance"):
    fim = (AGORA - dt.timedelta(hours=horas_atras)).isoformat()
    con.execute("insert into rodada(fonte, inicio, fim, status, conferida) values (?,?,?, 'ok', ?)", (fonte, fim, fim, conferida))


def _tipos(con):
    return sorted(r[0] for r in con.execute("select tipo from aviso"))


def _comp(con, id_, nome, venc, estado, valor=10000, doc="DOC-SECRETO", pix="chave-pix-secreta"):
    con.execute("insert into compromisso(id, nome, vencimento, valor_centavos, estado, dados) values (?,?,?,?,?,?)",
                (id_, nome, venc, valor, estado, json.dumps({"pix": pix, "documento": doc})))


def test_rodada_parada_depois_de_duas_nao_conferidas(con):
    _rodada(con, 3, 1); _rodada(con, 2, 0); _rodada(con, 1, 0)
    ids = gerar_avisos(con, AGORA)
    assert len(ids) == 1 and _tipos(con) == ["rodada_parada"]


def test_uma_rodada_nao_conferida_so_nao_avisa(con):
    _rodada(con, 3, 1); _rodada(con, 1, 0)
    assert gerar_avisos(con, AGORA) == []


def test_dados_com_mais_de_3_dias_avisam_mesmo_sem_rodada_recente(con):
    _rodada(con, 24 * 4, 1)
    gerar_avisos(con, AGORA)
    assert _tipos(con) == ["rodada_parada"]


def test_banco_vazio_nao_gera_aviso(con):
    assert gerar_avisos(con, AGORA) == []


def test_nao_duplica_aviso_aberto_no_mesmo_dia(con):
    _rodada(con, 2, 0); _rodada(con, 1, 0)
    assert len(gerar_avisos(con, AGORA)) == 1
    assert gerar_avisos(con, AGORA + dt.timedelta(hours=2)) == []
    assert gerar_avisos(con, AGORA + dt.timedelta(days=1)) != []           # no dia seguinte, se persiste, avisa de novo


def test_aviso_lido_nao_impede_o_proximo_do_mesmo_dia_se_o_problema_voltar(con):
    _rodada(con, 2, 0); _rodada(con, 1, 0)
    gerar_avisos(con, AGORA)
    con.execute("update aviso set entregue_em='x'")
    assert gerar_avisos(con, AGORA + dt.timedelta(hours=1)) == []          # já foi dado hoje; lido não reabre


def test_conta_atrasada_ha_mais_de_um_dia_gera_um_aviso_por_compromisso(con):
    _comp(con, "a:2026-10", "Cristina Yabe", "2026-10-14", "atrasado")
    _comp(con, "b:2026-10", "Hoje atrasado", "2026-10-16", "atrasado")      # venceu hoje: ainda não é atraso
    gerar_avisos(con, AGORA)
    assert _tipos(con) == ["conta_atrasada"]
    assert json.loads(con.execute("select payload from aviso").fetchone()[0])["nome"] == "Cristina Yabe"


def test_cobrada_apos_cancelar_gera_aviso(con):
    con.execute("insert into assinatura(estabelecimento, status, status_em, lembrar_ate_cancelar) values ('BRAND YOURSELF COM','cancelar','2026-09-20',1)")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, status) "
                "values (1,'l1','2026-10-02',-4499,'BRAND-YOURSELF.COM','BRAND YOURSELF COM','custo','posted')")
    gerar_avisos(con, AGORA)
    assert _tipos(con) == ["cobrada_apos_cancelar"]


def test_cobranca_anterior_ao_cancelamento_nao_avisa(con):
    con.execute("insert into assinatura(estabelecimento, status, status_em) values ('X','cancelar','2026-09-20')")
    con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, natureza, status) values (1,'l1','2026-09-01',-100,'X','X','custo','posted')")
    assert gerar_avisos(con, AGORA) == []


def test_vence_hoje_agrupa_em_um_aviso(con):
    _comp(con, "a:2026-10", "Thiago", "2026-10-16", "aberto", 350000)
    _comp(con, "b:2026-10", "Suzana", "2026-10-16", "previsto", 72000)
    _comp(con, "c:2026-10", "Pago", "2026-10-16", "pago")
    gerar_avisos(con, AGORA)
    p = json.loads(con.execute("select payload from aviso where tipo='vence_hoje'").fetchone()[0])
    assert [i["nome"] for i in p["itens"]] == ["Suzana", "Thiago"] and p["itens"][1]["valor"] == "3500.00"


def test_payload_nao_tem_dado_sensivel(con):
    _comp(con, "a:2026-10", "Cristina", "2026-10-14", "atrasado"); _comp(con, "b:2026-10", "Thiago", "2026-10-16", "aberto")
    _rodada(con, 2, 0); _rodada(con, 1, 0)
    gerar_avisos(con, AGORA)
    todos = " ".join(r[0] for r in con.execute("select payload from aviso"))
    assert "DOC-SECRETO" not in todos and "chave-pix-secreta" not in todos and "pix" not in todos.lower() and "documento" not in todos.lower()


def test_servico_falhou_registra_aviso_com_o_nome_da_unidade(con):
    from gabi.avisos import registrar_servico_falhou
    registrar_servico_falhou(con, "gabi-brain-saldos.service", AGORA)
    registrar_servico_falhou(con, "gabi-brain-saldos.service", AGORA)          # idempotente no dia
    p = json.loads(con.execute("select payload from aviso where tipo='servico_falhou'").fetchone()[0])
    assert p["unidade"] == "gabi-brain-saldos.service" and con.execute("select count(*) from aviso").fetchone()[0] == 1


def test_conta_atrasada_lida_nao_volta_no_dia_seguinte_e_nao_acumula_enquanto_nao_lida(con):
    _comp(con, "a:2026-10", "Cristina Yabe", "2026-10-14", "atrasado")
    gerar_avisos(con, AGORA)
    assert gerar_avisos(con, AGORA + dt.timedelta(days=1)) == []            # ainda não lido: não empilha outro igual
    con.execute("update aviso set entregue_em='x'")
    assert gerar_avisos(con, AGORA + dt.timedelta(days=2)) == []            # lido: silêncio por 7 dias
    assert len(gerar_avisos(con, AGORA + dt.timedelta(days=9))) == 1        # persiste depois disso: lembra de novo


def test_exportacao_parada_avisa_quando_passa_de_9_dias_sem_pacote(con):
    _rodada(con, 24 * 12, 1, fonte="backup")
    gerar_avisos(con, AGORA)
    assert "exportacao_parada" in _tipos(con)


def test_exportacao_recente_nao_avisa(con):
    _rodada(con, 24 * 12, 1, fonte="backup"); _rodada(con, 24 * 3, 0, fonte="exportacao")
    gerar_avisos(con, AGORA)
    assert "exportacao_parada" not in _tipos(con)


def test_descrever_tipos_da_escuta():
    from gabi.rotas.avisos import descrever
    t, x = descrever("escuta_atencao", {"numero": "+5511912345678", "nome": "Maria", "texto": "NAO"})
    assert t == "Possível crise: Maria. Abra a conversa." and "NAO" not in x and "NAO" not in t
    assert descrever("escuta_atencao", {"numero": "+5511912345678"})[0] == "Possível crise: +5511912345678. Abra a conversa."
    assert descrever("escuta_saude", {"numero": "+55119", "nome": "Ana"})[0] == "Mensagem de saúde de Ana: abra a conversa"
    for tipo, p in [("escuta_novo_remetente", {"numero": "+55119", "nome": None}), ("escuta_parada", {"motivo": "sem leitura"}),
                    ("escuta_sem_modelo", {}), ("escuta_pedido_incompleto", {"numero": "+55119", "nome": "Ana"})]:
        titulo, texto = descrever(tipo, p)
        assert titulo != tipo and titulo and not titulo.startswith("escuta_")


# ---------------- escuta_parada ----------------
def _param_escuta(con, chave, valor):
    import json as _j
    con.execute("insert or replace into parametro(chave, valor) values (?,?)", (chave, _j.dumps(valor)))


def _msg_em(con, horas_atras):
    quando = (AGORA - dt.timedelta(hours=horas_atras)).isoformat()
    con.execute("insert into escuta_msg(id_externo, de, recebida_em) values (?,?,?)", (f"x{horas_atras}", "+5511900000000", quando))


def test_aviso_escuta_parada_so_em_modo_ativo(con):
    _msg_em(con, 20)
    assert "escuta_parada" not in _tipos_novos(con)          # sem parametro = registro
    _param_escuta(con, "escuta.modo", "registro")
    assert "escuta_parada" not in _tipos_novos(con)
    _param_escuta(con, "escuta.modo", "ativo")
    gerar_avisos(con, AGORA)
    r = con.execute("select payload from aviso where tipo='escuta_parada'").fetchall()
    assert len(r) == 1 and "20 horas" in r[0][0]
    gerar_avisos(con, AGORA + dt.timedelta(hours=1))
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 1   # um por dia


def test_escuta_parada_respeita_limite_e_sem_mensagens(con):
    _param_escuta(con, "escuta.modo", "ativo")
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 0   # sem linhas = sem aviso
    _msg_em(con, 5)
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 0   # dentro das 12h
    _param_escuta(con, "escuta.horas_sem_receber", 4)
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 1


def _tipos_novos(con):
    gerar_avisos(con, AGORA)
    return [r[0] for r in con.execute("select tipo from aviso")]


def test_escuta_parada_compara_instantes_com_entradas_mistas(con):
    from gabi.escuta.caixa import _utc
    _param_escuta(con, "escuta.modo", "ativo")
    _param_escuta(con, "escuta.horas_sem_receber", 12)
    # AGORA = 12:00 UTC; 12h atrás = 00:00 UTC do mesmo dia = 21:00 BRT do dia anterior
    con.execute("insert into escuta_msg(id_externo, de, recebida_em) values ('a','+5511900000000',?)", (_utc("2026-10-15T21:30:00"),))   # ingênuo BRT = 00:30 UTC: 11,5h
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 0
    con.execute("update escuta_msg set recebida_em=?", (_utc("2026-10-15T20:30:00-03:00"),))   # 23:30 UTC: 12,5h
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where tipo='escuta_parada'").fetchone()[0] == 1


# ---- aviso obsoleto: produtor ----
def test_nao_cria_conta_atrasada_nem_vence_hoje_para_compromisso_pago(con):
    _comp(con, "a:2026-10", "Paga", "2026-10-14", "pago")
    _comp(con, "b:2026-10", "Paga hoje", "2026-10-16", "pago")
    assert gerar_avisos(con, AGORA) == []


def test_produtor_fecha_aviso_aberto_cuja_condicao_resolveu(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    _comp(con, "b:2026-10", "Outra", "2026-10-06", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(hours=6))
    con.execute("update compromisso set estado='pago' where id='a:2026-10'")
    gerar_avisos(con, AGORA)
    abertos = [json.loads(r[0])["nome"] for r in con.execute("select payload from aviso where entregue_em is null")]
    assert abertos == ["Outra"]
