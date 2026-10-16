import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.correio import processar as pr
from gabi.correio import sincronizar as sz
from gabi.db import conectar, migrar
from gabi.dinheiro.modelo import Orcamento
from gabi.fontes.google_oauth import ErroGoogleOAuth

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = "2026-10-12T12:00:00+00:00"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def _fonte(con, conta="a@x.com", estado="sim", lixeira=1, respondidos=True):
    f = con.execute("insert into email_fonte(conta, provedor, estado, lixeira) values (?, 'google', ?, ?)", (conta, estado, lixeira)).lastrowid
    if respondidos:
        sz.atualizar_respondidos(con, f, [], AGORA)  # "já conferi quem eu respondi" (lista vazia vale)
    return f


def _msg(con, f, ext, assunto="Oferta", de="promo@loja.com", lista=1, estado="nova", classe=None, thread=None, recebida="2026-10-12T10:00:00+00:00", trecho="texto"):
    return con.execute("insert into email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, trecho, lista, estado, classe) values (?,?,?,?,?,?,?,?,?,?)",
                       (f, ext, thread or ext + "t", de, assunto, recebida, trecho, lista, estado, classe)).lastrowid


def _json(classe="lixo", prioridade=0, motivo="promoção", confianca=0.95):
    return json.dumps({"classe": classe, "prioridade": prioridade, "motivo": motivo, "confianca": confianca})


class Modelo:
    """Responde conforme o assunto que aparece no prompt; `padrao` quando nenhum casa."""

    def __init__(self, por_assunto=None, padrao=None, erro=None, ao_completar=None):
        self.por_assunto, self.padrao, self.erro, self.n, self.ao_completar = por_assunto or {}, padrao or _json(), erro, 0, ao_completar

    def completar(self, prompt, *, forte):
        self.n += 1
        if self.ao_completar:
            self.ao_completar()
        if self.erro:
            raise self.erro
        for assunto, resp in self.por_assunto.items():
            if assunto in prompt:
                return resp, 0.001
        return self.padrao, 0.001


class Ponte:
    def __init__(self, erro_ids=(), levanta=None, respondeu=(), erro_respondeu=None):
        self.chamadas, self.erro_ids, self.levanta = [], set(erro_ids), levanta
        self.respondeu, self.erro_respondeu, self.consultas = set(respondeu), erro_respondeu, []

    def respondeu_a(self, conta, enderecos):
        self.consultas.append((conta, list(enderecos)))
        if self.erro_respondeu:
            raise self.erro_respondeu
        return {a: a in self.respondeu for a in enderecos}

    def lixeira(self, conta, ids):
        self.chamadas.append((conta, list(ids)))
        if self.levanta:
            raise self.levanta
        return {i: ("erro" if i in self.erro_ids else "ok") for i in ids}


def _orc():
    return Orcamento(1.0, 10.0)


def _estado(con, ext):
    r = con.execute("select estado, classe, tentativas, proxima_em from email_msg where externo_id=?", (ext,)).fetchone()
    return tuple(r)


def test_lixo_com_todas_as_condicoes_vai_a_lixeira_e_marca_na_lixeira(con):
    f = _fonte(con); _msg(con, f, "a1")
    p = Ponte()
    r = pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert p.chamadas == [("a@x.com", ["a1"])] and r["lixeira"] == 1
    m = con.execute("select estado, classe, prioridade, motivo, confianca, atualizado_em from email_msg").fetchone()
    assert (m["estado"], m["classe"], m["prioridade"], m["motivo"], m["confianca"], m["atualizado_em"]) == ("na_lixeira", "lixo", 0, "promoção", 0.95, AGORA)


def test_normal_e_importante_ficam_classificadas_sem_mover(con):
    f = _fonte(con); _msg(con, f, "a1", "Proposta", lista=0); _msg(con, f, "b2", "Fatura", lista=0)
    m = Modelo({"Proposta": _json("importante", 2, "cliente", 0.8), "Fatura": _json("normal", 1, "info", 0.7)})
    p = Ponte()
    r = pr.processar(con, m, _orc(), p, AGORA)
    assert p.chamadas == [] and r["classificadas"] == 2
    assert _estado(con, "a1")[:2] == ("classificada", "importante") and _estado(con, "b2")[:2] == ("classificada", "normal")


def test_protegido_nunca_vai_mesmo_com_modelo_dizendo_lixo_e_lista(con):
    f = _fonte(con)
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?, 'amigo@x.com', ?)", (f, AGORA))
    con.execute("insert into parametro(chave, valor) values ('email.vips', ?)", (json.dumps(["chefe@x.com"]),))
    _msg(con, f, "a1", de="amigo@x.com"); _msg(con, f, "b2", de="Chefe <chefe@x.com>"); _msg(con, f, "c3", de="")
    p = Ponte()
    pr.processar(con, Modelo(padrao=_json("lixo", 0, "x", 1.0)), _orc(), p, AGORA)
    assert p.chamadas == [] and {_estado(con, e)[0] for e in ("a1", "b2", "c3")} == {"classificada"}


def test_fonte_sem_conferencia_dos_respondidos_nao_move_nada(con):
    f = _fonte(con, respondidos=False); _msg(con, f, "a1")
    p = Ponte()
    r = pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert p.chamadas == [] and r["lixeira"] == 0 and _estado(con, "a1")[:2] == ("classificada", "lixo")


def test_conta_com_lixeira_zero_le_e_classifica_mas_nunca_move(con):
    f = _fonte(con, lixeira=0); _msg(con, f, "a1")
    p = Ponte()
    pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert p.chamadas == [] and _estado(con, "a1")[:2] == ("classificada", "lixo")


def test_fonte_a_decidir_ou_nao_nunca_e_processada(con):
    f = _fonte(con, estado="a_decidir"); g = _fonte(con, "b@x.com", estado="nao"); _msg(con, f, "a1"); _msg(con, g, "b2")
    m, p = Modelo(), Ponte()
    pr.processar(con, m, _orc(), p, AGORA)
    assert m.n == 0 and p.chamadas == [] and _estado(con, "a1")[0] == "nova" and _estado(con, "b2")[0] == "nova"


def test_falha_ao_mover_nao_marca_na_lixeira_e_tenta_de_novo_sem_pagar_o_modelo(con):
    f = _fonte(con); _msg(con, f, "a1")
    m, p = Modelo(), Ponte(erro_ids={"a1"})
    r = pr.processar(con, m, _orc(), p, AGORA)
    assert r["lixeira"] == 0 and r["adiadas"] == 1
    est, classe, tent, prox = _estado(con, "a1")
    assert (est, classe, tent) == ("nova", "lixo", 1) and prox == "2026-10-12T12:05:00+00:00"
    pr.processar(con, m, _orc(), p, "2026-10-12T12:04:00+00:00")  # antes da espera: não tenta
    assert len(p.chamadas) == 1
    p.erro_ids.clear()
    pr.processar(con, m, _orc(), p, "2026-10-12T12:06:00+00:00")
    assert _estado(con, "a1")[:2] == ("na_lixeira", "lixo") and m.n == 1  # a classificação já paga foi reaproveitada


def test_ponte_levantando_erro_tambem_adia_sem_marcar_e_sem_vazar(con, capsys):
    f = _fonte(con); _msg(con, f, "a1", "ASSUNTO-SECRETO")
    pr.processar(con, Modelo(), _orc(), Ponte(levanta=ErroGoogleOAuth("serviço de fontes indisponível")), AGORA)
    assert _estado(con, "a1")[:3] == ("nova", "lixo", 1)
    saida = capsys.readouterr()
    assert "SECRETO" not in saida.out + saida.err


def test_restaurada_nunca_volta_sozinha_a_lixeira(con):
    f = _fonte(con); _msg(con, f, "a1", estado="restaurada", classe="lixo")
    m, p = Modelo(), Ponte()
    pr.processar(con, m, _orc(), p, AGORA)
    pr.processar(con, m, _orc(), p, "2026-10-13T12:00:00+00:00")
    assert p.chamadas == [] and m.n == 0 and _estado(con, "a1")[0] == "restaurada"


def test_primeira_carga_grande_respeita_max_por_rodada_e_pega_as_mais_novas_primeiro(con):
    f = _fonte(con)
    for i in range(200):
        _msg(con, f, f"m{i:03d}", f"Oferta {i}", recebida=(dt.datetime(2026, 10, 12, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=i)).isoformat())
    m, p = Modelo(), Ponte()
    r = pr.processar(con, m, _orc(), p, AGORA, pr.Limites(max_por_rodada=60, tempo_max_s=210))
    assert m.n == 60 and r["lixeira"] == 60
    assert con.execute("select count(*) from email_msg where estado='nova'").fetchone()[0] == 140
    assert con.execute("select min(externo_id) from email_msg where estado='na_lixeira'").fetchone()[0] == "m140"  # as 60 mais recentes


def test_respeita_o_tempo_maximo_da_rodada(con):
    f = _fonte(con)
    for i in range(10):
        _msg(con, f, f"m{i}", f"Oferta {i}")
    relogio = iter(range(0, 1000, 100))  # cada leitura do relógio avança 100 s
    m = Modelo()
    r = pr.processar(con, m, _orc(), Ponte(), AGORA, pr.Limites(max_por_rodada=60, tempo_max_s=250), relogio=lambda: next(relogio))
    assert 0 < m.n < 10 and r["tempo"] is True


def test_mensagem_mais_velha_que_a_janela_nunca_e_tocada(con):
    f = _fonte(con); _msg(con, f, "velha", recebida="2026-09-01T10:00:00+00:00"); _msg(con, f, "nova1")
    m, p = Modelo(), Ponte()
    pr.processar(con, m, _orc(), p, AGORA)
    assert p.chamadas == [("a@x.com", ["nova1"])] and _estado(con, "velha")[0] == "nova"


def _avisos(con, tipo):
    return [json.loads(r["payload"]) for r in con.execute("select payload from aviso where tipo=? and entregue_em is null", (tipo,))]


def test_sem_modelo_nada_vai_a_lixeira_e_avisa_uma_vez_por_dia(con):
    f = _fonte(con); _msg(con, f, "a1")
    p = Ponte()
    r = pr.processar(con, None, _orc(), p, AGORA)
    pr.processar(con, None, _orc(), p, "2026-10-12T12:15:00+00:00")
    assert p.chamadas == [] and r["sem_modelo"] == 1 and _estado(con, "a1")[:3] == ("nova", None, 0)
    assert len(_avisos(con, "email_sem_modelo")) == 1 and "motivo" in _avisos(con, "email_sem_modelo")[0]


def test_teto_de_custo_para_o_modelo_nao_move_e_avisa(con):
    f = _fonte(con); _msg(con, f, "a1")
    p = Ponte()
    pr.processar(con, Modelo(), Orcamento(0.0, 0.0), p, AGORA)
    assert p.chamadas == [] and _estado(con, "a1")[:3] == ("nova", None, 0)
    assert "teto" in _avisos(con, "email_sem_modelo")[0]["motivo"]


def test_alerta_emergencial_um_por_conversa_e_nao_repete_ao_reler(con):
    f = _fonte(con)
    _msg(con, f, "a1", "Prazo vence hoje", lista=0, thread="T1"); _msg(con, f, "a2", "Re: Prazo vence hoje", lista=0, thread="T1")
    m = Modelo(padrao=_json("emergencial", 3, "prazo hoje", 0.9))
    r = pr.processar(con, m, _orc(), Ponte(), AGORA)
    assert r["emergenciais"] == 1 and len(_avisos(con, "email_emergencial")) == 1
    a = _avisos(con, "email_emergencial")[0]
    assert a["chave"] == "T1" and a["motivo"] == "prazo hoje" and a["remetente"] == "promo@loja.com" and a["assunto"] == "Re: Prazo vence hoje"  # a mensagem mais recente da conversa
    assert _estado(con, "a1")[0] == "alertada" and _estado(con, "a2")[0] == "alertada"
    _msg(con, f, "a3", "Re: Prazo vence hoje", lista=0, thread="T1")
    pr.processar(con, m, _orc(), Ponte(), "2026-10-13T12:00:00+00:00")  # dia seguinte, mesma conversa
    assert len(_avisos(con, "email_emergencial")) == 1


def test_emergencial_alerta_mesmo_em_conta_sem_lixeira(con):
    f = _fonte(con, lixeira=0); _msg(con, f, "a1", lista=0)
    pr.processar(con, Modelo(padrao=_json("emergencial", 3, "x", 0.9)), _orc(), Ponte(), AGORA)
    assert len(_avisos(con, "email_emergencial")) == 1


def test_fechar_alerta_fecha_o_aviso_da_conversa(con):
    f = _fonte(con); _msg(con, f, "a1", lista=0, thread="T1")
    pr.processar(con, Modelo(padrao=_json("emergencial", 3, "x", 0.9)), _orc(), Ponte(), AGORA)
    assert pr.fechar_alerta(con, "T1", AGORA) == 1 and _avisos(con, "email_emergencial") == []


def test_resposta_invalida_vira_normal_classificada_e_e_contada(con):
    f = _fonte(con); _msg(con, f, "a1")
    p = Ponte()
    r = pr.processar(con, Modelo(padrao="isto não é json"), _orc(), p, AGORA)
    assert r["invalidas"] == 1 and p.chamadas == [] and _estado(con, "a1")[:2] == ("classificada", "normal")


def test_falha_do_modelo_adia_com_backoff_e_na_oitava_vira_falhou(con, capsys):
    f = _fonte(con); _msg(con, f, "a1", "ASSUNTO-SECRETO")
    m = Modelo(erro=RuntimeError("boom ASSUNTO-SECRETO"))
    agora = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)
    esperas = []
    for n in range(8):
        pr.processar(con, m, _orc(), Ponte(), agora.isoformat())
        est, _, tent, prox = _estado(con, "a1")
        if est == "nova":
            esperas.append((dt.datetime.fromisoformat(prox) - agora).total_seconds() / 60)
        agora += dt.timedelta(hours=7)
    assert esperas == [5, 10, 20, 40, 80, 160, 320] and _estado(con, "a1")[:3] == ("falhou", None, 8)
    saida = capsys.readouterr()
    assert "SECRETO" not in saida.out + saida.err


def test_resumo_do_dia_so_depois_das_18h_e_uma_vez(con):
    f = _fonte(con)
    for i in range(12):
        _msg(con, f, f"a{i}", f"Oferta {i}", estado="na_lixeira")
    con.execute("update email_msg set atualizado_em='2026-10-12T15:00:00+00:00'")  # 12h BRT
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 20, 0, tzinfo=dt.timezone.utc)) is None  # 17h BRT: cedo
    assert _avisos(con, "email_lixeira_resumo") == []
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 21, 30, tzinfo=dt.timezone.utc)) is not None  # 18h30 BRT
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.timezone.utc)) is None
    a = _avisos(con, "email_lixeira_resumo")
    assert len(a) == 1 and a[0]["total"] == 12 and len(a[0]["itens"]) == 10 and set(a[0]["itens"][0]) == {"remetente", "assunto"}


def test_resumo_do_dia_sem_nada_na_lixeira_nao_avisa(con):
    f = _fonte(con); _msg(con, f, "a1", estado="classificada")
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.timezone.utc)) is None and _avisos(con, "email_lixeira_resumo") == []


def test_resumo_do_dia_so_conta_o_que_foi_para_a_lixeira_hoje(con):
    f = _fonte(con); _msg(con, f, "ontem", estado="na_lixeira"); _msg(con, f, "hoje", estado="na_lixeira")
    con.execute("update email_msg set atualizado_em='2026-10-11T15:00:00+00:00' where externo_id='ontem'")
    con.execute("update email_msg set atualizado_em='2026-10-12T15:00:00+00:00' where externo_id='hoje'")
    pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 22, 0, tzinfo=dt.timezone.utc))
    assert _avisos(con, "email_lixeira_resumo")[0]["total"] == 1


def test_purgar_trechos_apaga_so_o_texto_e_mantem_o_estado(con):
    f = _fonte(con)
    _msg(con, f, "velha", recebida="2026-09-01T10:00:00+00:00", estado="classificada"); _msg(con, f, "recente")
    n = pr.purgar_trechos(con, AGORA, 30)
    assert n == 1
    assert con.execute("select trecho, estado, assunto from email_msg where externo_id='velha'").fetchone()[:] == (None, "classificada", "Oferta")
    assert con.execute("select trecho from email_msg where externo_id='recente'").fetchone()[0] == "texto"


def _n(con, tabela="email_msg"):
    return {r[0] for r in con.execute(f"select externo_id from {tabela}")} if tabela == "email_msg" else {r[0] for r in con.execute(f"select endereco from {tabela}")}


def test_purgar_mensagens_poda_por_idade_e_preserva_lixeira_recuperavel_e_pendentes(con):
    f = _fonte(con)
    velha = "2026-01-01T10:00:00+00:00"
    for ext, estado in (("class", "classificada"), ("alert", "alertada"), ("rest", "restaurada"), ("falhou", "falhou"), ("lix_rec", "na_lixeira"), ("lix_velha", "na_lixeira"), ("nova", "nova")):
        _msg(con, f, ext, estado=estado, recebida=velha)
    _msg(con, f, "recente", estado="classificada")
    con.execute("update email_msg set atualizado_em='2026-10-05T10:00:00+00:00' where externo_id='lix_rec'")   # movida há 7 dias: o Gmail ainda guarda
    con.execute("update email_msg set atualizado_em='2026-08-01T10:00:00+00:00' where externo_id='lix_velha'")  # movida há mais de 30 dias
    n = pr.purgar_mensagens(con, AGORA, 180)
    assert n == 5
    assert _n(con) == {"lix_rec", "nova", "recente"}


def test_purgar_mensagens_poda_respondidos_so_depois_da_janela_dos_enviados_e_guarda_a_sentinela(con):
    f = _fonte(con)
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?,?,?)", (f, "antigo@x.com", "2025-01-01T00:00:00+00:00"))
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?,?,?)", (f, "meio@x.com", "2026-02-01T00:00:00+00:00"))   # 8 meses: dentro dos 365 d da conferência
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?,?,?)", (f, "novo@x.com", "2026-10-01T00:00:00+00:00"))
    pr.purgar_mensagens(con, AGORA, 180)
    assert _n(con, "email_respondido") == {"", "meio@x.com", "novo@x.com"}
    assert sz.respondidos_prontos(con, f)


def test_retencao_msg_dias_do_banco_tem_padrao_180_e_piso_90(con):
    assert pr.retencao_msg_dias(con) == 180
    for bruto, esperado in (("365", 365), ("30", 180), ("\"x\"", 180), ("true", 180), ("5000", 180)):
        con.execute("insert into parametro(chave, valor) values ('email.retencao_msg_dias', ?) on conflict(chave) do update set valor=excluded.valor", (bruto,))
        assert pr.retencao_msg_dias(con) == esperado


def test_limites_do_banco_usa_parametros_com_padrao_e_ignora_lixo(con):
    assert pr.limites_do_banco(con) == pr.Limites(60, 210)
    con.execute("insert into parametro(chave, valor) values ('email.max_por_rodada', '10'), ('email.tempo_max_s', '\"muito\"')")
    assert pr.limites_do_banco(con) == pr.Limites(10, 210)


# ---------------- passada de correções da revisão final ----------------
def test_remetente_que_o_dono_respondeu_fora_da_lista_nao_e_movido(con):
    f = _fonte(con); _msg(con, f, "a1", de="suporte@fornecedor.com")
    p = Ponte(respondeu={"suporte@fornecedor.com"})
    r = pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert p.chamadas == [] and r["lixeira"] == 0 and _estado(con, "a1")[:2] == ("classificada", "lixo")


def test_conferencia_ao_vivo_pergunta_uma_vez_por_remetente(con):
    f = _fonte(con)
    for i in range(3):
        _msg(con, f, f"a{i}", de="promo@loja.com")
    _msg(con, f, "b1", de="outra@loja.com")
    p = Ponte()
    pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert len(p.consultas) == 1 and p.consultas[0][0] == "a@x.com" and sorted(p.consultas[0][1]) == ["outra@loja.com", "promo@loja.com"]
    assert len(p.chamadas) == 1 and len(p.chamadas[0][1]) == 4


def test_falha_na_conferencia_ao_vivo_adia_e_nao_move(con):
    f = _fonte(con); _msg(con, f, "a1")
    p = Ponte(erro_respondeu=ErroGoogleOAuth("messages.list -> 500"))
    r = pr.processar(con, Modelo(), _orc(), p, AGORA)
    assert p.chamadas == [] and r["adiadas"] == 1 and _estado(con, "a1")[:3] == ("nova", "lixo", 1)  # na dúvida fica na caixa e tenta de novo


def test_palavra_protegida_nunca_vai_e_nao_gasta_consulta(con):
    f = _fonte(con); _msg(con, f, "a1", "Sua fatura vence amanhã"); _msg(con, f, "b2", "Aviso", trecho="o boleto está disponível")
    p = Ponte()
    pr.processar(con, Modelo(padrao=_json("lixo", 0, "x", 1.0)), _orc(), p, AGORA)
    assert p.chamadas == [] and p.consultas == [] and {_estado(con, e)[0] for e in ("a1", "b2")} == {"classificada"}


def test_desligar_a_lixeira_no_meio_da_rodada_nao_move(con):
    f = _fonte(con); _msg(con, f, "a1")
    m = Modelo(ao_completar=lambda: con.execute("update email_fonte set lixeira=0"))
    p = Ponte()
    r = pr.processar(con, m, _orc(), p, AGORA)
    assert p.chamadas == [] and r["lixeira"] == 0 and _estado(con, "a1")[:2] == ("classificada", "lixo")


def test_desligar_a_conta_no_meio_da_rodada_nao_move(con):
    f = _fonte(con); _msg(con, f, "a1")
    m = Modelo(ao_completar=lambda: con.execute("update email_fonte set estado='nao'"))
    p = Ponte()
    pr.processar(con, m, _orc(), p, AGORA)
    assert p.chamadas == [] and _estado(con, "a1")[0] == "classificada"


def test_alerta_so_para_mensagem_recente_a_antiga_continua_visivel_sem_alertar(con):
    f = _fonte(con)
    _msg(con, f, "velha", lista=0, thread="T1", recebida="2026-10-07T10:00:00+00:00")  # 5 dias
    _msg(con, f, "nova1", lista=0, thread="T2", recebida="2026-10-12T10:00:00+00:00")
    r = pr.processar(con, Modelo(padrao=_json("emergencial", 3, "x", 0.9)), _orc(), Ponte(), AGORA)
    assert r["emergenciais"] == 1 and [a["chave"] for a in _avisos(con, "email_emergencial")] == ["T2"]
    assert _estado(con, "velha")[:2] == ("classificada", "emergencial")  # fica na fila de prioridades, sem notificar o celular


def test_teto_diario_de_alertas_agrupa_o_excesso_num_aviso_so(con):
    f = _fonte(con)
    con.execute("insert into parametro(chave, valor) values ('email.max_alertas_dia', '2')")
    for i in range(5):
        _msg(con, f, f"e{i}", lista=0, thread=f"T{i}")
    r = pr.processar(con, Modelo(padrao=_json("emergencial", 3, "x", 0.9)), _orc(), Ponte(), AGORA)
    chaves = sorted(a["chave"] for a in _avisos(con, "email_emergencial"))
    assert r["emergenciais"] == 2 and len(chaves) == 3 and sum(1 for c in chaves if c.startswith("excesso-")) == 1
    estados = sorted(_estado(con, f"e{i}")[0] for i in range(5))
    assert estados == ["alertada", "alertada", "classificada", "classificada", "classificada"]  # o excesso continua nas prioridades
    pr.processar(con, Modelo(padrao=_json("emergencial", 3, "x", 0.9)), _orc(), Ponte(), "2026-10-12T12:30:00+00:00")
    assert len(_avisos(con, "email_emergencial")) == 3  # o aviso de excesso não se repete no mesmo dia


def test_mensagem_que_vira_falhou_gera_um_aviso_com_a_contagem(con):
    f = _fonte(con); _msg(con, f, "a1"); _msg(con, f, "b2")
    m = Modelo(erro=RuntimeError("boom"))
    agora = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)
    for _ in range(8):
        pr.processar(con, m, _orc(), Ponte(), agora.isoformat())
        agora += dt.timedelta(hours=7)
    avisos = _avisos(con, "email_falhou")
    assert len(avisos) == 1 and avisos[0]["total"] == 2 and set(avisos[0]) == {"chave", "total"}  # só a contagem, nunca texto


def test_resumo_cobre_o_que_veio_depois_do_ultimo_resumo(con):
    f = _fonte(con)
    for i in range(3):
        _msg(con, f, f"a{i}", estado="na_lixeira")
    con.execute("update email_msg set atualizado_em='2026-10-12T15:00:00+00:00'")
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 12, 21, 30, tzinfo=dt.timezone.utc)) is not None
    for i in range(12):
        _msg(con, f, f"b{i}", estado="na_lixeira")
    con.execute("update email_msg set atualizado_em='2026-10-12T23:00:00+00:00' where externo_id like 'b%'")  # 20h BRT: depois do resumo
    assert pr.resumo_do_dia(con, dt.datetime(2026, 10, 13, 21, 30, tzinfo=dt.timezone.utc)) is not None
    totais = sorted(a["total"] for a in _avisos(con, "email_lixeira_resumo"))
    assert totais == [3, 12]  # nada se perde: o que veio depois das 18h entra no resumo do dia seguinte, sem repetir o que já foi dito


def test_limites_novos_do_banco_alertas_e_dias(con):
    assert pr.alertas_por_dia(con) == 5
    con.execute("insert into parametro(chave, valor) values ('email.max_alertas_dia', '0')")
    assert pr.alertas_por_dia(con) == 5  # inválido cai no padrão


@pytest.mark.parametrize("bruto,vai", [("0.5", False), ("0.0", False), ("0.69", False), ("0.7", True)])
def test_limiar_da_lixeira_tem_piso_07_no_banco_editado_a_mao(con, bruto, vai):
    """E-mail M9 (fechado): valor abaixo de 0,7 lido do banco cai no padrão 0,9; confiança 0,75 só passa com limiar >= 0,7 e <= 0,75."""
    con.execute("insert into parametro(chave, valor) values ('email.lixeira_confianca', ?)", (bruto,))
    f = _fonte(con)
    _msg(con, f, "m1")
    pr.processar(con, Modelo(padrao=_json("lixo", 0, "promoção", 0.75)), _orc(), Ponte(), AGORA)
    assert (_estado(con, "m1")[0] == "na_lixeira") is vai
