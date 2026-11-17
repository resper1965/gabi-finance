"""O corte do gabi-finance: a superfície (rotas HTTP e ferramentas MCP) é só financeira. Listas exatas, para que nada volte sem ser visto."""
from pathlib import Path

from gabi.api import criar_app
from gabi.db import conectar, migrar
from gabi.mcp.servidor import ESCOPOS_FERRAMENTAS, criar_mcp, ferramentas_do_hermes

MIGRACOES = Path(__file__).parent.parent / "migrations"

# base de hoje (saúde, identidade, painel) + dinheiro, gastos, cadastros (financeiro), despesas, cobrar, decisões, avisos, agentes e contagens
ROTAS = [
    "DELETE /api/v1/cadastros/categorias/equivalencias/{origem}",
    "DELETE /api/v1/cadastros/{tipo}/{id_}",
    "DELETE /api/v1/despesas/{id_}",
    "DELETE /api/v1/despesas/{id_}/mes/{mes}/dispensar",
    "GET /",
    "GET /api/eu",
    "GET /api/saude",
    "GET /api/seguranca",
    "GET /api/v1/agentes",
    "GET /api/v1/agentes/conexao",
    "GET /api/v1/agentes/{id_}/chamadas",
    "GET /api/v1/assinaturas",
    "GET /api/v1/avisos",
    "GET /api/v1/cadastros/categorias/equivalencias",
    "GET /api/v1/cadastros/categorias/equivalencias/pendentes",
    "GET /api/v1/cadastros/nibo",
    "GET /api/v1/cadastros/{tipo}",
    "GET /api/v1/cadastros/{tipo}/{id_}",
    "GET /api/v1/caixa/projecao",
    "GET /api/v1/caixa/resumo",
    "GET /api/v1/caixa/semanas",
    "GET /api/v1/cartoes",
    "GET /api/v1/cobrar/a-receber",
    "GET /api/v1/cobrar/notas",
    "GET /api/v1/cobrar/previsao",
    "GET /api/v1/cobrar/recebimentos",
    "GET /api/v1/contagens",
    "GET /api/v1/contas-pagar",
    "GET /api/v1/custo",
    "GET /api/v1/decisoes/perguntas",
    "GET /api/v1/despesas",
    "GET /api/v1/destino",
    "GET /api/v1/destino/agrupado",
    "GET /api/v1/fontes",
    "GET /api/v1/lancamentos",
    "GET /api/v1/parcelas",
    "GET /api/v1/regras",
    "GET /api/v1/rodadas",
    "GET /api/v1/rumo",
    "GET /api/v1/sugestoes",
    "PATCH /api/v1/agentes/{id_}/escopos",
    "PATCH /api/v1/assinaturas/{aid}",
    "PATCH /api/v1/cadastros/{tipo}/{id_}",
    "PATCH /api/v1/despesas/{id_}",
    "PATCH /api/v1/lancamentos/{lid}",
    "PATCH /api/v1/regras/{rid}",
    "POST /api/revogar-tudo",
    "POST /api/v1/agentes",
    "POST /api/v1/agentes/{id_}/revogar",
    "POST /api/v1/agentes/{id_}/rotacionar",
    "POST /api/v1/avisos/{aviso_id}/lido",
    "POST /api/v1/cadastros/{tipo}",
    "POST /api/v1/cobrar/a-receber-manual/propostas/{pid}/confirmar",
    "POST /api/v1/cobrar/a-receber-manual/propostas/{pid}/rejeitar",
    "POST /api/v1/cobrar/a-receber-manual/{rid}/cancelar",
    "POST /api/v1/cobrar/recebimentos/{rid}/confirmar",
    "POST /api/v1/cobrar/recebimentos/{rid}/rejeitar",
    "POST /api/v1/contas-pagar/{id_compromisso}/paga",
    "POST /api/v1/decisoes/perguntas",
    "POST /api/v1/despesas",
    "POST /api/v1/despesas/{id_}/encerrar",
    "POST /api/v1/despesas/{id_}/mes/{mes}",
    "POST /api/v1/despesas/{id_}/mes/{mes}/dispensar",
    "POST /api/v1/lancamentos/lote",
    "POST /api/v1/sugestoes/{sid}/aprovar",
    "POST /api/v1/sugestoes/{sid}/rejeitar",
    "PUT /api/v1/cadastros/categorias/equivalencias",
    "PUT /api/v1/cadastros/nibo",
]

# as financeiras de hoje, com os mesmos nomes (F8); o resto (agenda, e-mail, Teams, contatos, família, documentos, projetos, atividades, assistente) saiu
FERRAMENTAS = [
    "agenda_financeira", "assinatura_marcar", "assinaturas_listar", "avisos_abertos", "classificar_lancamento", "decisao_responder", "decisoes_abertas",
    "decisoes_recentes", "despesa_criar", "despesa_encerrar", "despesa_excluir", "despesa_mes", "despesa_mudar", "despesas_listar", "despesas_por_empresa",
    "empresas_listar", "fechamento_dia", "financeiro_a_receber", "financeiro_cancelar_a_receber", "financeiro_contas_a_pagar", "financeiro_indicar_gastador",
    "financeiro_lancamentos", "financeiro_marcar_gasto", "financeiro_marcar_reembolso", "financeiro_para_onde_vai", "financeiro_previsao",
    "financeiro_recorrentes", "financeiro_registrar_a_receber", "financeiro_saldo", "regras_listar", "regras_sugerir", "resumo_manha",
]


def _banco(tmp_path):
    p = tmp_path / "g.db"
    c = conectar(p)
    migrar(c, MIGRACOES)
    c.close()
    return p


def test_rotas_registradas_sao_so_as_financeiras_e_as_de_base(tmp_path):
    app = criar_app(_banco(tmp_path), permite_tcp_local=True)
    registradas = sorted(f"{m.upper()} {p}" for p, ops in app.openapi()["paths"].items() for m in ops)
    assert registradas == ROTAS
    for fora in ("/api/v1/agenda", "/api/v1/correio", "/api/v1/teams", "/api/v1/contatos", "/api/v1/envios", "/api/v1/familia", "/api/v1/documentos",
                 "/api/v1/projetos", "/api/v1/atividades", "/api/v1/hoje", "/api/v1/gabi/qualidade"):
        assert not [r for r in registradas if f" {fora}" in r], fora


def test_cadastros_so_financeiro_sem_a_consulta_de_documento_da_familia(tmp_path):
    app = criar_app(_banco(tmp_path), permite_tcp_local=True)
    paths = set(app.openapi()["paths"])
    assert "/api/v1/cadastros/pessoas/{pid}/cpf" not in paths
    assert {"/api/v1/cadastros/nibo", "/api/v1/cadastros/categorias/equivalencias", "/api/v1/cadastros/{tipo}"} <= paths


def test_ferramentas_do_hermes_sao_so_as_financeiras():
    assert ferramentas_do_hermes() == FERRAMENTAS
    assert sorted(ESCOPOS_FERRAMENTAS) == FERRAMENTAS


def test_servidor_mcp_se_anuncia_como_gabi_finance(tmp_path):
    app = criar_mcp(_banco(tmp_path), hosts=["127.0.0.1:8081"])
    assert app.servidor.name == "gabi_finance"
