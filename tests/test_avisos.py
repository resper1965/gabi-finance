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
    assert [i["id"] for i in p["itens"]] == ["b:2026-10", "a:2026-10"]  # o produtor grava o id do compromisso em cada item
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


def test_produtor_nao_fecha_aviso_incerto_a_conferir(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(hours=6))
    con.execute("update compromisso set estado='a_conferir'")
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where entregue_em is null").fetchone()[0] == 1
    con.execute("delete from compromisso")
    gerar_avisos(con, AGORA)
    assert con.execute("select count(*) from aviso where entregue_em is null").fetchone()[0] == 1


# ---- incerto vencido (round 2) ----
def _abertos(con):
    return con.execute("select count(*) from aviso where entregue_em is null").fetchone()[0]


def test_produtor_fecha_incerto_mais_velho_que_a_janela_sem_enviar_e_mantem_o_mais_novo(con):
    _comp(con, "a:2026-10", "Velha", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(days=3))
    con.execute("update compromisso set estado='a_conferir'")
    _comp(con, "b:2026-10", "Nova", "2026-10-06", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(hours=12))
    con.execute("update compromisso set estado='a_conferir' where id='b:2026-10'")
    gerar_avisos(con, AGORA)
    r = {json.loads(x["payload"])["nome"]: x for x in con.execute("select * from aviso")}
    assert r["Velha"]["entregue_em"] and r["Velha"]["telegram_em"] == r["Velha"]["entregue_em"]
    assert r["Nova"]["entregue_em"] is None and r["Nova"]["telegram_em"] is None


def test_a_conferir_por_3_dias_e_depois_atrasado_gera_aviso_novo_e_e_enviado(con):
    from gabi.telegram import enviar_avisos_contagem
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(days=3))
    con.execute("update compromisso set estado='a_conferir'")
    gerar_avisos(con, AGORA - dt.timedelta(hours=1))   # fecha o velho (incerto fora da janela)
    con.execute("update compromisso set estado='atrasado'")
    assert len(gerar_avisos(con, AGORA)) == 1
    chamadas = []
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
    assert enviar_avisos_contagem(con, env, AGORA, lambda u, c: chamadas.append(c) or 200) == (1, 0, 0) and len(chamadas) == 1


def test_aviso_velho_aberto_nao_enviado_nao_bloqueia_um_novo(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(days=3))
    assert len(gerar_avisos(con, AGORA)) == 1   # o velho (aberto, fora da janela, nunca enviado) não segura o novo


def test_silencio_semanal_vale_para_aviso_realmente_entregue(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(days=3))
    con.execute("update aviso set telegram_em=?, entregue_em=?", ((AGORA - dt.timedelta(days=3)).isoformat(), (AGORA - dt.timedelta(days=2)).isoformat()))
    assert gerar_avisos(con, AGORA) == []
    # e o aviso ainda aberto mas já enviado ao Telegram também segura
    con.execute("update aviso set entregue_em=null")
    assert gerar_avisos(con, AGORA) == []


# ---- round 3: enviado-e-resolvido fecha; duplicados consolidados ----
def test_aviso_enviado_e_depois_pago_e_fechado_so_com_entregue_em(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(hours=6))
    enviado = (AGORA - dt.timedelta(hours=5)).isoformat()
    con.execute("update aviso set telegram_em=?", (enviado,))
    con.execute("update compromisso set estado='pago'")
    gerar_avisos(con, AGORA)
    r = con.execute("select telegram_em, entregue_em from aviso").fetchone()
    assert r["entregue_em"] and r["telegram_em"] == enviado  # telegram_em segue significando "enviado"


def test_aviso_incerto_enviado_e_nao_lido_fica_aberto_mesmo_fora_da_janela(con):
    _comp(con, "a:2026-10", "XP", "2026-10-05", "atrasado")
    gerar_avisos(con, AGORA - dt.timedelta(days=4))
    con.execute("update aviso set telegram_em=?", ((AGORA - dt.timedelta(days=4)).isoformat(),))
    con.execute("update compromisso set estado='a_conferir'")
    gerar_avisos(con, AGORA)
    assert _abertos(con) == 1


def _tres_contas(con):
    for i in range(3):
        _comp(con, f"c{i}:2026-10", f"Conta{i}", "2026-10-05", "atrasado")


def _por_conta_abertos(con):
    r = {}
    for x in con.execute("select payload from aviso where entregue_em is null"):
        k = json.loads(x[0])["chave"]
        r[k] = r.get(k, 0) + 1
    return r


def test_telegram_desligado_5_dias_no_maximo_um_aberto_por_conta(con):
    _tres_contas(con)
    t = AGORA - dt.timedelta(days=5)
    while t <= AGORA:
        gerar_avisos(con, t)
        t += dt.timedelta(hours=6)
    assert con.execute("select count(*) from aviso").fetchone()[0] > 3  # houve renovação...
    assert _por_conta_abertos(con) == {"c0:2026-10": 1, "c1:2026-10": 1, "c2:2026-10": 1}  # ...mas só o mais recente fica aberto
    # superados fechados sem envio: telegram_em == entregue_em
    from gabi.telegram import enviar_avisos_contagem
    chamadas = []
    assert enviar_avisos_contagem(con, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}, AGORA, lambda u, c: chamadas.append(c) or 200) == (3, 0, 0)
    assert len(chamadas) == 3


def test_sem_produtor_o_telegram_tambem_consolida_duplicados(con):
    from gabi.telegram import enviar_avisos_contagem
    _tres_contas(con)
    for dias in (1, 0.5, 0.1):   # três avisos por conta, todos dentro da janela
        for i in range(3):
            con.execute("insert into aviso(tipo, payload, criado_em) values ('conta_atrasada', ?, ?)",
                        (json.dumps({"chave": f"c{i}:2026-10", "nome": f"Conta{i}", "vencimento": "2026-10-05", "valor": "1"}), (AGORA - dt.timedelta(days=dias)).isoformat()))
    chamadas = []
    assert enviar_avisos_contagem(con, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}, AGORA, lambda u, c: chamadas.append(c) or 200) == (3, 0, 0)
    assert con.execute("select count(*) from aviso where telegram_em is not null").fetchone()[0] == 9  # 3 enviados + 6 superados


# ---------------- hermes_parado (H4) ----------------
def test_hermes_parado_avisa_uma_vez_por_dia(con):
    gerar_avisos(con, AGORA, estado_servico=lambda u: "failed")
    gerar_avisos(con, AGORA + dt.timedelta(hours=1), estado_servico=lambda u: "failed")
    r = con.execute("select payload from aviso where tipo='hermes_parado'").fetchall()
    assert len(r) == 1 and json.loads(r[0][0]) == {"chave": "hermes-gateway", "unidade": "hermes-gateway", "estado": "failed"}


def test_hermes_ativo_subindo_ou_desconhecido_nao_avisa(con):
    for st in ("active", "activating", "reloading", None):
        gerar_avisos(con, AGORA, estado_servico=lambda u, st=st: st)
    assert con.execute("select count(*) from aviso where tipo='hermes_parado'").fetchone()[0] == 0


def test_sem_leitor_de_servico_ninguem_consulta_o_systemd(con):
    gerar_avisos(con, AGORA)  # padrão dos testes e de quem não passa o leitor
    assert con.execute("select count(*) from aviso where tipo='hermes_parado'").fetchone()[0] == 0


def test_hermes_parado_pode_ser_desligado_e_a_unidade_trocada(con):
    _param_escuta(con, "avisos.vigiar_hermes", False)
    gerar_avisos(con, AGORA, estado_servico=lambda u: "failed")
    assert con.execute("select count(*) from aviso where tipo='hermes_parado'").fetchone()[0] == 0
    _param_escuta(con, "avisos.vigiar_hermes", True)
    _param_escuta(con, "avisos.hermes_unidade", "outro-gateway")
    chamadas = []
    gerar_avisos(con, AGORA, estado_servico=lambda u: chamadas.append(u) or "inactive")
    assert chamadas == ["outro-gateway"]


def test_descrever_hermes_parado():
    from gabi.rotas.avisos import descrever
    t, x = descrever("hermes_parado", {"unidade": "hermes-gateway", "estado": "failed"})
    assert "Hermes" in t and "restart hermes-gateway" in x and "failed" in x


def test_estado_do_servico_devolve_none_quando_nao_ha_systemd_ou_unidade():
    from gabi.avisos import estado_do_servico
    assert estado_do_servico("unidade-que-nao-existe-xyz") is None


def test_servico_falhou_nao_empilha_enquanto_nao_lido_e_fica_mudo_depois_de_lido(con):
    from gabi.avisos import registrar_servico_falhou
    registrar_servico_falhou(con, "gabi-brain-notas.service", AGORA)
    assert registrar_servico_falhou(con, "gabi-brain-notas.service", AGORA + dt.timedelta(days=1)) is None   # a unidade segue falhando: um aviso só
    assert registrar_servico_falhou(con, "gabi-brain-saldos.service", AGORA + dt.timedelta(days=1)) is not None   # outra unidade tem o seu
    con.execute("update aviso set entregue_em='x'")
    assert registrar_servico_falhou(con, "gabi-brain-notas.service", AGORA + dt.timedelta(days=2)) is None   # lido: silêncio por 7 dias
    assert registrar_servico_falhou(con, "gabi-brain-notas.service", AGORA + dt.timedelta(days=9)) is not None
