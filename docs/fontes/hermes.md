# Hermes (Canal) · como o gabi-finance o enxerga
O Hermes é **só interface**: lê e propõe pelo MCP, não guarda dado (trocar de agente não perde nada). A instalação do Hermes é do plano mestre; esta página é o lado do gabi-finance.

## Conexão ao MCP (TC.2)
Token emitido pelo painel/CLI com os escopos `fin, trabalho, propostas, pedidos, decisoes` (nunca `sensivel`), colado pelo Ricardo no `.env` do Hermes (R5). Config do Hermes:

```yaml
mcp_servers:
  gabi_finance:
    url: http://127.0.0.1:8082/mcp
    headers:
      Authorization: Bearer ${GABI_FINANCE_TOKEN}
    tools:
      include:
      - agenda_financeira
      - assinatura_marcar
      - assinaturas_listar
      - avisos_abertos
      - classificar_lancamento
      - decisao_responder
      - decisoes_abertas
      - decisoes_recentes
      - despesa_criar
      - despesa_encerrar
      - despesa_excluir
      - despesa_mes
      - despesa_mudar
      - despesas_listar
      - despesas_por_empresa
      - empresas_listar
      - fechamento_dia
      - financeiro_a_receber
      - financeiro_cancelar_a_receber
      - financeiro_contas_a_pagar
      - financeiro_indicar_gastador
      - financeiro_lancamentos
      - financeiro_marcar_gasto
      - financeiro_marcar_reembolso
      - financeiro_para_onde_vai
      - financeiro_previsao
      - financeiro_recorrentes
      - financeiro_registrar_a_receber
      - financeiro_saldo
      - olhar_a_frente
      - regras_listar
      - regras_sugerir
      - resumo_manha
```
A lista é a **explícita** (sem `*`) e é testada: `tests/mcp/test_hermes.py` falha se ela divergir das ferramentas dos escopos acima. Regerar: `python -m tools.gerar_hermes`.
Se o Streamable HTTP falhar no Hermes, usar `transport: sse` e registrar aqui.

## Rodadas (TC.3)
- Avisos: o Hermes lê `avisos_abertos` (só leitura; não há ferramenta de confirmar entrega). O envio dos avisos ao Telegram é do `gabi-finance-telegram` (timer de 5 em 5 minutos), não do Hermes.
- 07:05: `resumo_manha` (até 5 linhas; a primeira é "⚠ Dados desatualizados…" quando for o caso) e, se quiser mais, `financeiro_contas_a_pagar`.

## Identidade (TC.4): ver `docs/adr/007-identidade-por-remetente.md`
