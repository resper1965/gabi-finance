import datetime as dt
from pathlib import Path

import pytest

from gabi.cobrar.lote_nibo import ConfirmacaoDivergente, executar_baixa, executar_lote, montar_lote, texto_baixa
from gabi.db import conectar, migrar
from gabi.fontes.nibo import ErroNibo

MIGRACOES = Path(__file__).parent.parent.parent / "migrations"
DIA = dt.date(2026, 10, 9)


class NiboFalso:
    """Guarda os agendamentos por `reference`, como o Nibo de verdade; conta as chamadas de escrita."""
    def __init__(self, falhar_em=()):
        self.agendamentos, self.anexos, self.baixas, self.criacoes = {}, {}, [], 0
        self.falhar_em = set(falhar_em)

    def agendamento_por_reference(self, ref):
        return self.agendamentos.get(ref)

    def criar_agendamento_debito(self, *, stakeholder_id, valor_centavos, data, category_id, descricao, reference):
        if reference in self.falhar_em:
            raise ErroNibo("500: limite excedido")
        self.criacoes += 1
        sid = f"sch-{self.criacoes}"
        self.agendamentos[reference] = {"scheduleId": sid, "value": valor_centavos, "stakeholderId": stakeholder_id, "categoryId": category_id}
        return sid

    def anexar_arquivo(self, schedule_id, nome, conteudo):
        self.anexos[schedule_id] = (nome, conteudo)

    def baixar_pagamento(self, schedule_id, *, account_id, data, valor_centavos, identifier):
        self.baixas.append((schedule_id, account_id, data, valor_centavos, identifier))


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "g.db")
    migrar(c, MIGRACOES)
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pf','Itau','BANK','Itaú PF',0,'sim')")   # 1
    c.execute("insert into conta(externo_id, instituicao, tipo, apelido, pj, estado) values ('pj','C6','BANK','C6 PJ',1,'sim')")       # 2
    c.execute("insert into empresa(id, nome, relacao) values ('bekaa','Bekaa','pj_titular')")
    c.execute("insert into empresa(id, nome, relacao) values ('ness','Ness','contratante')")
    c.execute("insert into categoria(nome, nibo_category_id) values ('Software','cat-sw')")
    c.execute("insert into parametro(chave, valor) values ('nibo_socio_id', '\"socio-ricardo\"')")
    return c


def _l(con, i, data, valor, conta=1, empresa="bekaa", cat=1, desc="LICENCA X"):
    return con.execute("insert into lancamento(conta_id, externo_id, data, valor_centavos, descricao_original, estabelecimento, empresa_id, categoria_id, status) "
                       "values (?,?,?,?,?,?,?,?, 'posted')", (conta, f"l{i}", data, valor, desc, desc, empresa, cat)).lastrowid


def _lote_confirmado(con, nibo=None, **kw):
    lote = montar_lote(con, DIA)
    return lote, executar_lote(con, lote.id, lote.texto_confirmacao, nibo or NiboFalso(), **kw)


def test_so_despesa_da_bekaa_paga_no_pf_entra(con):
    a = _l(con, 1, "2026-10-01", -10000)                         # entra
    _l(con, 2, "2026-10-02", -5000, conta=2)                      # paga pela PJ: não
    _l(con, 3, "2026-10-03", 8000)                                # entrada: não
    _l(con, 4, "2026-10-04", -3000, empresa=None)                 # sem empresa: não
    assert [i.lancamento_id for i in montar_lote(con, DIA).itens] == [a]


def test_ness_e_ionic_nunca_entram_no_lote(con):
    _l(con, 1, "2026-10-01", -10000, empresa="ness")
    assert montar_lote(con, DIA).itens == []


def test_texto_de_confirmacao_tem_N_e_valor_exatos(con):
    _l(con, 1, "2026-10-01", -123456)
    _l(con, 2, "2026-10-02", -50000)
    assert montar_lote(con, DIA).texto_confirmacao == "Lançar no Nibo da Bekaa: 2 despesas, R$ 1.734,56."


def test_confirmacao_divergente_409_e_nada_grava(con):
    _l(con, 1, "2026-10-01", -10000)
    lote, nibo = montar_lote(con, DIA), NiboFalso()
    with pytest.raises(ConfirmacaoDivergente):
        executar_lote(con, lote.id, "Lançar no Nibo da Bekaa: 1 despesas, R$ 100,01.", nibo)  # um centavo diferente
    assert nibo.criacoes == 0 and nibo.agendamentos == {}
    assert con.execute("select estado from lote_nibo where id=?", (lote.id,)).fetchone()[0] == "montado"


def test_executar_cria_o_agendamento_com_reference_e_dados_do_gasto(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    nibo = NiboFalso()
    _, r = _lote_confirmado(con, nibo)
    assert (r.ok, r.erro) == (1, 0)
    ag = nibo.agendamentos[f"gabi:{lid}"]
    assert ag["value"] == 10000 and ag["stakeholderId"] == "socio-ricardo" and ag["categoryId"] == "cat-sw"
    assert con.execute("select estado from lote_nibo").fetchone()[0] == "executado"


def test_executar_duas_vezes_nao_duplica(con):
    _l(con, 1, "2026-10-01", -10000)
    nibo = NiboFalso()
    lote, _ = _lote_confirmado(con, nibo)
    r2 = executar_lote(con, lote.id, lote.texto_confirmacao, nibo)  # mesma confirmação, de novo
    assert nibo.criacoes == 1 and (r2.ok, r2.erro) == (0, 0)
    lote2 = montar_lote(con, DIA)  # e um novo lote não repesca o que já foi
    assert lote2.itens == []


def test_reference_ja_existente_no_nibo_pula_a_criacao(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    nibo = NiboFalso()
    nibo.agendamentos[f"gabi:{lid}"] = {"scheduleId": "ja-existia"}  # criado por uma execução anterior que caiu no meio
    _, r = _lote_confirmado(con, nibo)
    assert nibo.criacoes == 0 and r.ok == 1
    assert con.execute("select schedule_id from lote_nibo_item").fetchone()[0] == "ja-existia"


def test_erro_em_um_item_nao_desfaz_os_outros_e_reprocessa(con):
    a, b = _l(con, 1, "2026-10-01", -10000), _l(con, 2, "2026-10-02", -20000)
    nibo = NiboFalso(falhar_em={f"gabi:{a}"})
    _, r = _lote_confirmado(con, nibo)
    assert (r.ok, r.erro) == (1, 1) and f"gabi:{b}" in nibo.agendamentos and f"gabi:{a}" not in nibo.agendamentos
    est = dict(con.execute("select lancamento_id, estado from lote_nibo_item").fetchall())
    assert est == {a: "erro", b: "ok"}
    nibo.falhar_em.clear()  # o próximo lote repesca só o que falhou
    lote2 = montar_lote(con, DIA)
    assert [i.lancamento_id for i in lote2.itens] == [a]
    assert executar_lote(con, lote2.id, lote2.texto_confirmacao, nibo).ok == 1 and nibo.criacoes == 2


def test_categoria_sem_equivalente_no_nibo_vira_erro_sem_chamar_o_nibo(con):
    con.execute("insert into categoria(nome) values ('Sem Nibo')")
    lid = _l(con, 1, "2026-10-01", -10000, cat=2)
    nibo = NiboFalso()
    _, r = _lote_confirmado(con, nibo)
    assert (r.ok, r.erro) == (0, 1) and nibo.criacoes == 0
    assert "categoria" in con.execute("select erro from lote_nibo_item where lancamento_id=?", (lid,)).fetchone()[0]


def test_sem_socio_cadastrado_nao_executa_nada(con):
    con.execute("delete from parametro where chave='nibo_socio_id'")
    _l(con, 1, "2026-10-01", -10000)
    lote, nibo = montar_lote(con, DIA), NiboFalso()
    with pytest.raises(ValueError, match="sócio"):
        executar_lote(con, lote.id, lote.texto_confirmacao, nibo)
    assert nibo.criacoes == 0


def test_anexa_o_comprovante_confirmado_quando_ha(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    cid = con.execute("insert into comprovante(paperless_id, tipo, valor_centavos, data) values (77,'comprovante_pix',10000,'2026-10-01')").lastrowid
    con.execute("insert into comprovante_vinculo(comprovante_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'x','confirmado','2026-10-01')", (cid, lid))
    nibo = NiboFalso()
    _lote_confirmado(con, nibo, baixar_comprovante=lambda paperless_id: (f"comprovante-{paperless_id}.pdf", b"%PDF-"))
    assert nibo.anexos["sch-1"] == ("comprovante-77.pdf", b"%PDF-")


def test_baixa_de_pagamento_tambem_exige_confirmacao(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    nibo = NiboFalso()
    _lote_confirmado(con, nibo)
    credito = _l(con, 9, "2026-10-12", 10000, conta=2, empresa=None, cat=None, desc="PIX BEKAA")
    texto = texto_baixa(con, lid, credito)
    assert "R$ 100,00" in texto and "Baixar no Nibo" in texto
    with pytest.raises(ConfirmacaoDivergente):
        executar_baixa(con, lid, credito, "baixar", nibo, account_id="c6pj")
    assert nibo.baixas == []
    executar_baixa(con, lid, credito, texto, nibo, account_id="c6pj")
    assert nibo.baixas == [("sch-1", "c6pj", "2026-10-12", 10000, f"gabi:baixa:{credito}")]
    executar_baixa(con, lid, credito, texto, nibo, account_id="c6pj")  # repetir não baixa de novo
    assert len(nibo.baixas) == 1


def test_baixa_exige_credito_pj_do_mesmo_valor(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    _lote_confirmado(con)
    errado = _l(con, 9, "2026-10-12", 9999, conta=2, empresa=None, cat=None)
    with pytest.raises(ValueError):
        texto_baixa(con, lid, errado)


def test_anexo_que_falha_deixa_o_item_em_erro_e_o_reprocesso_so_anexa(con):
    lid = _l(con, 1, "2026-10-01", -10000)
    cid = con.execute("insert into comprovante(paperless_id, tipo, valor_centavos, data) values (77,'comprovante_pix',10000,'2026-10-01')").lastrowid
    con.execute("insert into comprovante_vinculo(comprovante_id, lancamento_id, confianca, motivo, estado, criado_em) values (?,?,1,'x','confirmado','2026-10-01')", (cid, lid))
    nibo = NiboFalso()

    def paperless_fora(_):
        raise ErroNibo("paperless indisponível")

    _, r = _lote_confirmado(con, nibo, baixar_comprovante=paperless_fora)
    assert (r.ok, r.erro) == (0, 1) and nibo.criacoes == 1 and nibo.anexos == {}
    lote2 = montar_lote(con, DIA)
    r2 = executar_lote(con, lote2.id, lote2.texto_confirmacao, nibo, baixar_comprovante=lambda p: ("c.pdf", b"x"))
    assert r2.ok == 1 and nibo.criacoes == 1 and "sch-1" in nibo.anexos  # não criou outro agendamento; só anexou
