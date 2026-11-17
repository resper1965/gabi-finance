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

## O que sai do `gabi_brain` na virada
No servidor antigo `gabi_brain` do `config.yaml`, tire do `include` **só** estas 28 ferramentas (só de dinheiro). Ficam nos dois servidores, com o mesmo nome: `avisos_abertos`, `resumo_manha`, `decisoes_abertas`, `decisoes_recentes` e `decisao_responder` (o dinheiro delas vem do `gabi_finance`; agenda, e-mail, família e projetos, do `gabi_brain`, que com `GABI_SEM_FINANCEIRO=1` não traz mais dinheiro). Gerada por `python -m tools.gerar_hermes` e testada em `tests/mcp/test_hermes.py`.

```
# tirar do include do gabi_brain:
- agenda_financeira
- assinatura_marcar
- assinaturas_listar
- classificar_lancamento
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
```

## Rodadas (TC.3)
- Avisos: o Hermes lê `avisos_abertos` (só leitura; não há ferramenta de confirmar entrega). O envio dos avisos ao Telegram é do `gabi-finance-telegram` (timer de 5 em 5 minutos), não do Hermes.
- 07:05: `resumo_manha` (até 5 linhas; a primeira é "⚠ Dados desatualizados…" quando for o caso) e, se quiser mais, `financeiro_contas_a_pagar`.

## Identidade (TC.4): ver `docs/adr/007-identidade-por-remetente.md`
