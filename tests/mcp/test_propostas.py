import json

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
    for n in nomes - {"familia_atualizar_contato", "email_remover_regra_lixo", "despesa_criar", "despesa_excluir", "atividade_criar", "projeto_criar", "projeto_ligar", "projeto_atualizar"}:  # escrita reversível a pedido do Ricardo (contato com Desfazer; Onda 3: lixeira, regra de lixo, a receber; ADR-032: despesas; ADR-033: atividade_criar)
        assert not (set(n.replace("contas_a_pagar", "contas").split("_")) & proibidas), n
    assert set(ESCOPOS_FERRAMENTAS) == nomes  # toda ferramenta tem escopo declarado


def test_propostas_criam_pendente_e_nunca_efetivam(cli2, banco2, tokens2):
    chamar(cli2, tokens2["propostas"], "classificar_lancamento", lancamento_id=2, categoria_id=2, motivo="UBER é transporte")
    chamar(cli2, tokens2["propostas"], "regras_sugerir", padrao="UBER", categoria_id=2, motivo="6 ocorrências")
    c = conectar(banco2)
    assert [r["estado"] for r in c.execute("select estado from sugestao order by id")] == ["pendente"] * 2
    assert c.execute("select count(*) from regra").fetchone()[0] == 0
    assert c.execute("select categoria_id, categoria_origem from lancamento where id=2").fetchone()[0] == 2  # inalterado (já era 2, 'voce')
    assert c.execute("select categoria_origem from lancamento where id=2").fetchone()[0] == "voce"


def test_classificar_nao_sobrescreve_decisao_do_ricardo_nem_efetiva(cli2, banco2, tokens2):
    chamar(cli2, tokens2["propostas"], "classificar_lancamento", lancamento_id=2, categoria_id=1, motivo="talvez mercado")
    c = conectar(banco2)
    assert c.execute("select categoria_id from lancamento where id=2").fetchone()[0] == 2  # a proposta não muda nada
    assert c.execute("select count(*) from sugestao where estado='pendente'").fetchone()[0] == 1


def test_documentos_baixar_exige_escopo_docs(cli2, tokens2):
    assert chamar(cli2, tokens2["propostas"], "documentos_baixar", id=5)["erro"] == "sem_escopo"
    d = chamar(cli2, tokens2["docs"], "documentos_baixar", id=5)["dados"]
    assert d["id"] == 5 and d["pdf_base64"]


def test_documentos_buscar_devolve_metadados_trecho_e_referencia(cli2, tokens2):
    itens = chamar(cli2, tokens2["docs"], "documentos_buscar", texto="luz")["dados"]["itens"]
    assert itens == [{"id": 5, "titulo": "Boleto luz", "criado_em": "2026-10-01", "trecho": "ENEL",
                      "referencia": {"paperless_id": 5, "titulo": "Boleto luz", "criado_em": "2026-10-01"}}]


def test_documentos_sem_paperless_configurado_devolve_fonte_indisponivel(banco2, tokens2):
    with TestClient(criar_mcp(banco2, hosts=[HOST], relogio=lambda: AGORA), base_url=f"http://{HOST}") as c:
        assert chamar(c, tokens2["docs"], "documentos_buscar", texto="x")["erro"] == "fonte_indisponivel"
