import json
import re

import pytest
from starlette.testclient import TestClient

from gabi.db import conectar
from gabi.fontes.paperless import Paperless
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp
from gabi.mcp.tokens import emitir
from tests.cobrar.paperless_falso import PaperlessFalso
from tests.mcp.test_servidor import AGORA, HOST, PERMITIDAS, banco, chamar, rpc  # noqa: F401  (fixtures e helpers)


@pytest.fixture
def banco2(banco):
    c = conectar(banco)
    c.execute("insert into empresa(id, nome, dados) values ('ness','Ness', ?)", (json.dumps({"relacao": "contratante", "email_cobranca": "fin@ness.com.br"}),))
    c.execute("update conta set pj=0 where id=1")
    c.execute("update lancamento set empresa_id='ness' where id=2")  # UBER TRIP -22,50 pago no PF para a Ness
    c.execute("insert into pessoa(id, nome, dados) values ('ana','Ana',?)",
              (json.dumps({"canais": ["whatsapp:+5511911110000"], "pode_pedir": True, "documentos": [{"tipo": "CPF", "numero": "123.456.789-09"}]}),))
    c.close()
    return banco


@pytest.fixture
def tokens2(banco2):
    c = conectar(banco2)
    t = {k: emitir(c, k, [k]) for k in ("fin", "docs", "propostas", "pedidos", "sensivel")}
    c.close()
    return t


@pytest.fixture
def paperless():
    return Paperless("http://p", "tok", http=PaperlessFalso(docs=[{"id": 5, "title": "Boleto luz", "created": "2026-10-01", "tags": [], "content": "ENEL"}]))


@pytest.fixture
def cli2(banco2, paperless):
    app = criar_mcp(banco2, hosts=[HOST], relogio=lambda: AGORA, paperless=paperless)
    with TestClient(app, base_url=f"http://{HOST}") as c:
        yield c


def test_lista_tem_as_ferramentas_novas_e_nenhuma_destrutiva(cli2, tokens2):
    nomes = {t["name"] for t in rpc(cli2, tokens2["fin"], "tools/list").json()["result"]["tools"]}
    assert nomes == PERMITIDAS
    proibidas = {"enviar", "apagar", "aprovar", "ligar", "excluir", "deletar", "remover", "transferir", "pagar", "criar", "atualizar", "decidir"}
    for n in nomes:
        assert not (set(n.replace("contas_a_pagar", "contas").split("_")) & proibidas), n
    assert set(ESCOPOS_FERRAMENTAS) == nomes  # toda ferramenta tem escopo declarado


def test_propostas_criam_pendente_e_nunca_efetivam(cli2, banco2, tokens2):
    chamar(cli2, tokens2["propostas"], "classificar_lancamento", lancamento_id=2, categoria_id=2, motivo="UBER é transporte")
    chamar(cli2, tokens2["propostas"], "regras_sugerir", padrao="UBER", categoria_id=2, motivo="6 ocorrências")
    chamar(cli2, tokens2["propostas"], "tarefas_propor", titulo="Cobrar a Ness", motivo="reembolso em aberto")
    c = conectar(banco2)
    assert [r["estado"] for r in c.execute("select estado from sugestao order by id")] == ["pendente"] * 3
    assert c.execute("select count(*) from regra").fetchone()[0] == 0
    assert c.execute("select categoria_id, categoria_origem from lancamento where id=2").fetchone()[0] == 2  # inalterado (já era 2, 'voce')
    assert c.execute("select categoria_origem from lancamento where id=2").fetchone()[0] == "voce"


def test_classificar_nao_sobrescreve_decisao_do_ricardo_nem_efetiva(cli2, banco2, tokens2):
    chamar(cli2, tokens2["propostas"], "classificar_lancamento", lancamento_id=2, categoria_id=1, motivo="talvez mercado")
    c = conectar(banco2)
    assert c.execute("select categoria_id from lancamento where id=2").fetchone()[0] == 2  # a proposta não muda nada
    assert c.execute("select count(*) from sugestao where estado='pendente'").fetchone()[0] == 1


def test_reembolsos_preparar_email_nao_envia(cli2, banco2, tokens2):
    r = chamar(cli2, tokens2["propostas"], "reembolsos_preparar_email", empresa_id="ness")
    d = r["dados"]
    assert d["rascunho"] is True and d["para"] == "fin@ness.com.br" and d["itens"] == 1 and "enviado" not in json.dumps(d).lower()
    assert conectar(banco2).execute("select count(*) from cobranca").fetchone()[0] == 1


def test_reembolsos_listar_exige_escopo_fin(cli2, tokens2):
    assert chamar(cli2, tokens2["docs"], "reembolsos_listar")["erro"] == "sem_escopo"
    d = chamar(cli2, tokens2["fin"], "reembolsos_listar")["dados"]
    assert d["empresas"][0]["empresa_id"] == "ness" and d["empresas"][0]["em_aberto"] == "22.50"


def test_documentos_baixar_exige_escopo_docs(cli2, tokens2):
    assert chamar(cli2, tokens2["propostas"], "documentos_baixar", id=5)["erro"] == "sem_escopo"
    d = chamar(cli2, tokens2["docs"], "documentos_baixar", id=5)["dados"]
    assert d["id"] == 5 and d["pdf_base64"]


def test_documentos_buscar_devolve_so_metadados(cli2, tokens2):
    itens = chamar(cli2, tokens2["docs"], "documentos_buscar", texto="luz")["dados"]["itens"]
    assert itens == [{"id": 5, "titulo": "Boleto luz", "criado_em": "2026-10-01"}]


def test_documentos_sem_paperless_configurado_devolve_fonte_indisponivel(banco2, tokens2):
    with TestClient(criar_mcp(banco2, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        assert chamar(c, tokens2["docs"], "documentos_buscar", texto="x")["erro"] == "fonte_indisponivel"


def test_pedido_de_quem_nao_pode_pedir_devolve_sem_escopo(cli2, banco2, tokens2):
    r = chamar(cli2, tokens2["pedidos"], "pedidos_registrar", solicitante="whatsapp:+5500000000", canal="whatsapp", mensagem_original="paga?",
               descricao="X", valor="10,00")
    assert r["erro"] == "sem_escopo" and conectar(banco2).execute("select count(*) from pedido").fetchone()[0] == 0


def test_pedido_registrado_nunca_diz_que_pagou_e_fica_pendente(cli2, banco2, tokens2):
    r = chamar(cli2, tokens2["pedidos"], "pedidos_registrar", solicitante="whatsapp:+5511911110000", canal="whatsapp", mensagem_original="paga o dentista?",
               descricao="Dentista", valor="R$ 150,00", vencimento="2026-10-20")["dados"]
    assert r["estado"] == "pendente" and not re.search(r"pag", r["texto_para_responder"], re.I)
    e = chamar(cli2, tokens2["pedidos"], "pedidos_estado", pedido_id=r["pedido_id"])["dados"]
    assert e["estado"] == "pendente"


def test_avisos_so_saem_da_fila_apos_a_confirmacao_do_canal(cli2, banco2, tokens2):
    from gabi.cobrar.pedidos import decidir
    c = conectar(banco2)
    pid = c.execute("insert into pedido(solicitante_pessoa_id, canal, mensagem_original, descricao, valor_centavos, criado_em) "
                    "values ('ana','whatsapp','x','Dentista',15000,'2026-10-09T10:00:00')").lastrowid
    decidir(c, pid, "recusar", "boss@x.com", mensagem="Não dá.")
    c.close()
    av = chamar(cli2, tokens2["pedidos"], "avisos_pendentes")["dados"]["itens"]
    assert len(av) == 1 and av[0]["payload"]["mensagem"] == "Não dá."
    assert len(chamar(cli2, tokens2["pedidos"], "avisos_pendentes")["dados"]["itens"]) == 1  # ler não tira da fila
    chamar(cli2, tokens2["pedidos"], "avisos_confirmar_entrega", aviso_id=av[0]["id"])
    assert chamar(cli2, tokens2["pedidos"], "avisos_pendentes")["dados"]["itens"] == []


def test_pessoas_dado_sem_liberacao_devolve_aguardando_liberacao(cli2, banco2, tokens2):
    r = chamar(cli2, tokens2["sensivel"], "pessoas_dado", pessoa_id="ana", campo="cpf")["dados"]
    assert r == {"status": "aguardando_liberacao", "pessoa_id": "ana", "campo": "cpf"}
    assert "123.456" not in json.dumps(r)
    c = conectar(banco2)
    c.execute("insert into liberacao_sensivel(pessoa_id, campo, liberado_por, liberado_em) values ('ana','cpf','boss@x.com','2026-10-09T10:00:00')")
    c.close()
    ok = chamar(cli2, tokens2["sensivel"], "pessoas_dado", pessoa_id="ana", campo="cpf")["dados"]
    assert ok["status"] == "liberado" and ok["valor"] == "123.456.789-09"
    de_novo = chamar(cli2, tokens2["sensivel"], "pessoas_dado", pessoa_id="ana", campo="cpf")["dados"]
    assert de_novo["status"] == "aguardando_liberacao"  # liberação única: uma leitura
    assert conectar(banco2).execute("select count(*) from chamada_mcp where ferramenta='pessoas_dado' and status='ok'").fetchone()[0] == 3


def test_pessoas_dado_exige_escopo_sensivel(cli2, tokens2):
    assert chamar(cli2, tokens2["fin"], "pessoas_dado", pessoa_id="ana", campo="cpf")["erro"] == "sem_escopo"
