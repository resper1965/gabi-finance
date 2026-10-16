import datetime as dt
import json
from pathlib import Path

import pytest

from gabi.db import conectar, migrar
from gabi.trabalho import contatos

MIGR = Path(__file__).parent.parent.parent / "migrations"
AGORA = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)  # segunda, 12:00 BRT


def iso(**kw):
    return (AGORA + dt.timedelta(**kw)).isoformat()


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "t.db")
    migrar(c, MIGR)
    return c


def fonte(con, conta="eu@x.com", estado="sim"):
    return con.execute("insert into email_fonte(conta, provedor, estado) values (?, 'google', ?)", (conta, estado)).lastrowid


def msg(con, f, remetente, classe="importante", dias=3, ext=None, estado="classificada", lista=0, assunto="ASSUNTO-SECRETO"):
    return con.execute("insert into email_msg(fonte_id, externo_id, remetente, assunto, recebida_em, classe, estado, lista) values (?,?,?,?,?,?,?,?)",
                       (f, ext or f"m{con.total_changes}-{remetente}-{dias}", remetente, assunto, iso(days=-dias), classe, estado, lista)).lastrowid


def pessoa(con, id_, nome, **dados):
    con.execute("insert into pessoa(id, nome, dados) values (?,?,?)", (id_, nome, json.dumps(dados)))


def itens(con, **kw):
    return contatos.contatos_em_aberto(con, AGORA, **kw)["itens"]


def test_sem_nada_em_aberto(con):
    assert contatos.contatos_em_aberto(con, AGORA) == {"total": 0, "itens": []}


def test_email_importante_sem_resposta_com_dias(con):
    msg(con, fonte(con), "Ana Souza <ana@y.com>", "importante", dias=3)
    [c] = itens(con)
    assert c["nome"] == "Ana Souza" and c["tipos"] == ["email"]
    a = c["abertos"][0]
    assert a["rotulo"] == "E-mail importante sem resposta" and a["dias"] == 3 and a["rota"] == {"area": "msgs", "aba": "prioridades"}


def test_email_ja_respondido_nao_aparece(con):
    f = fonte(con)
    msg(con, f, "ana@y.com")
    con.execute("insert into email_respondido(fonte_id, endereco, em) values (?,?,?)", (f, "ana@y.com", iso()))
    assert itens(con) == []


def test_nao_conta_lixo_lixeira_lista_nem_fora_da_janela(con):
    f = fonte(con)
    msg(con, f, "a@y.com", "lixo"); msg(con, f, "b@y.com", estado="na_lixeira"); msg(con, f, "c@y.com", lista=1)
    msg(con, f, "d@y.com", "normal"); msg(con, f, "e@y.com", dias=20)
    assert itens(con) == []


def test_caixa_nao_liberada_fica_fora(con):
    msg(con, fonte(con, "outra@x.com", "a_decidir"), "ana@y.com", "emergencial")
    msg(con, fonte(con, "nao@x.com", "nao"), "bia@y.com", "emergencial")
    assert itens(con) == []


def test_ordena_por_urgencia_emergencial_primeiro(con):
    f = fonte(con)
    msg(con, f, "velha@y.com", "importante", dias=6)
    msg(con, f, "grave@y.com", "emergencial", dias=1)
    assert [c["nome"] for c in itens(con)] == ["grave@y.com", "velha@y.com"]
    assert itens(con)[0]["abertos"][0]["rotulo"] == "E-mail emergencial sem resposta"


def test_varios_emails_viram_uma_linha_com_o_mais_antigo(con):
    f = fonte(con)
    msg(con, f, "ana@y.com", dias=2); msg(con, f, "ana@y.com", "emergencial", dias=5)
    [c] = itens(con)
    a = c["abertos"][0]
    assert a["qtd"] == 2 and a["dias"] == 5 and a["rotulo"] == "E-mail emergencial sem resposta (2)"


def test_pessoa_cadastrada_junta_email_e_whatsapp(con):
    pessoa(con, "p-ana", "Ana Cadastrada", canais=["email:ana@y.com", "whatsapp:+5511987654321"])
    msg(con, fonte(con), "Outro Nome <ana@y.com>")
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, texto, estado, tipo) values ('w1','+5511987654321',?,'TEXTO-PRIVADO','processada','pedido')", (iso(days=1),))
    [c] = itens(con)
    assert c["nome"] == "Ana Cadastrada" and c["tipos"] == ["email", "whatsapp"] and c["pessoa_id"] == "p-ana"


def _evento(con, cx, inicio, participantes, titulo="Reunião com Ana"):
    con.execute("insert into evento(caixa_id, externo_id, inicio, fim, titulo, participantes) values (?,?,?,?,?,?)",
                (cx, f"e{con.total_changes}", inicio, inicio, titulo, json.dumps(participantes)))


def caixa(con, estado="sim"):
    return con.execute("insert into caixa_email(endereco, provedor, estado) values ('eu@x.com','google',?)", (estado,)).lastrowid


def test_reuniao_proxima_conta_e_passada_ou_distante_nao(con):
    cx = caixa(con)
    _evento(con, cx, iso(days=1), ["eu@x.com", "ana@y.com"])
    _evento(con, cx, iso(days=-1), ["velha@y.com"])      # passada
    _evento(con, cx, iso(days=9), ["longe@y.com"])       # além de 7 dias
    _evento(con, cx, iso(hours=-1), ["agora@y.com"])      # já começou
    [c] = itens(con)
    assert c["nome"] == "ana@y.com" and c["tipos"] == ["agenda"]
    assert c["abertos"][0]["rotulo"] == "Reunião amanhã" and c["urgencia"] == 1 and c["abertos"][0]["rota"]["area"] == "agenda"


def test_reuniao_de_caixa_nao_liberada_fica_fora(con):
    _evento(con, caixa(con, "a_decidir"), iso(days=1), ["ana@y.com"])
    assert itens(con) == []


def test_politica_de_agenda_privada_mascara_o_titulo(con):
    _evento(con, caixa(con), iso(days=2), ["ana@y.com"], titulo="Consulta médica")
    assert itens(con)[0]["abertos"][0]["detalhe"] == "Consulta médica"
    con.execute("insert into parametro(chave, valor) values ('agenda.privados','\"so_painel\"')")
    assert itens(con, painel=True)[0]["abertos"][0]["detalhe"] == "Consulta médica"
    assert itens(con, painel=False)[0]["abertos"][0]["detalhe"] == "Compromisso privado"
    con.execute("update parametro set valor='\"ocultar\"' where chave='agenda.privados'")
    assert itens(con, painel=True)[0]["abertos"][0]["detalhe"] == "Compromisso privado"


def test_pedido_aberto_ligado_a_pessoa(con):
    pessoa(con, "p-bia", "Bia")
    con.execute("insert into pedido(solicitante_pessoa_id, canal, mensagem_original, descricao, estado, criado_em) values ('p-bia','whatsapp','TEXTO-X','pagar luz','pendente',?)", (iso(days=-4),))
    con.execute("insert into pedido(solicitante_pessoa_id, canal, mensagem_original, descricao, estado, criado_em) values ('p-bia','whatsapp','Y','pagar gás','aprovado',?)", (iso(days=-9),))
    [c] = itens(con)
    assert c["abertos"][0]["rotulo"] == "Pedido aguardando você" and c["abertos"][0]["dias"] == 4
    assert "TEXTO-X" not in json.dumps(c) and "pagar luz" not in json.dumps(c)


def test_whatsapp_so_contagem_e_data_nunca_o_texto(con):
    for i, d in enumerate((1, 3)):
        con.execute("insert into escuta_msg(id_externo, de, recebida_em, texto, estado, tipo, campos) values (?,?,?,?,?,?,?)",
                    (f"w{i}", "+5511987654321", iso(days=-d), "SEGREDO-DA-MENSAGEM", "retida", "pedido", '{"descricao":"CAMPO-SECRETO"}'))
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, texto, estado, tipo) values ('g','+5511900000000',?,'GRUPO','processada','pedido')", (iso(days=-1),))
    con.execute("update escuta_msg set grupo=1 where id_externo='g'")
    saida = contatos.contatos_em_aberto(con, AGORA)
    [c] = saida["itens"]
    bruto = json.dumps(saida)
    assert "SEGREDO" not in bruto and "CAMPO-SECRETO" not in bruto and "987654321" not in bruto
    a = c["abertos"][0]
    assert c["nome"] == "+55 *******4321" and a["qtd"] == 2 and a["dias"] == 3 and a["rotulo"] == "Pediu algo no WhatsApp (2 mensagens)"


def test_whatsapp_nome_pelo_remetente_e_bloqueado_fora(con):
    con.execute("insert into escuta_remetente(numero, nome, estado) values ('+5511911111111','Carlos','aprovado'), ('+5511922222222','Chato','bloqueado')")
    for n in ("+5511911111111", "+5511922222222"):
        con.execute("insert into escuta_msg(id_externo, de, recebida_em, estado, tipo) values (?,?,?,'retida','pedido')", (n, n, iso(days=-1)))
    [c] = itens(con)
    assert c["nome"] == "Carlos" and c["abertos"][0]["detalhe"] == "+55 *******1111"


def test_whatsapp_ja_virou_pedido_nao_duplica(con):
    pessoa(con, "p-d", "Dora", canais=["whatsapp:+5511933333333"])
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, estado, tipo) values ('d','+5511933333333',?,'processada','pedido')", (iso(days=-2),))
    con.execute("insert into pedido(solicitante_pessoa_id, canal, mensagem_original, descricao, estado, criado_em) values ('p-d','escuta','x','y','pendente',?)", (iso(days=-2, minutes=1),))
    [c] = itens(con)
    assert c["tipos"] == ["pedido"]


def test_whatsapp_antigo_e_outros_tipos_nao_contam(con):
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, estado, tipo) values ('a','+5511944444444',?,'retida','pedido')", (iso(days=-30),))
    con.execute("insert into escuta_msg(id_externo, de, recebida_em, estado, tipo) values ('b','+5511955555555',?,'processada','nada')", (iso(days=-1),))
    assert itens(con) == []


def test_email_dispensado_pelo_dono_nao_aparece(con):
    f = fonte(con)
    i = msg(con, f, "ana@y.com")
    assert len(itens(con)) == 1
    con.execute("update email_msg set dispensada_em=? where id=?", (iso(), i))
    assert itens(con) == []
