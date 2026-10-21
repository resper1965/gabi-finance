# Hermes (Canal) · como o gabi.brain o enxerga
O Hermes é **só interface**: lê e propõe pelo MCP, não guarda dado (trocar de agente não perde nada). Instalação, OpenRouter e WhatsApp seguem o plano mestre (TC.1, TC.5);
**instalar o Hermes e desligar o OpenClaw só depois do término do gabi.brain** (decisão do Ricardo, 08/10). Esta página é o lado do gabi.brain.

## Conexão ao MCP (TC.2)
Token emitido pelo painel/CLI com os escopos `fin, docs, trabalho, propostas, pedidos, decisoes` (nunca `sensivel`), colado pelo Ricardo no `.env` do Hermes (R5). Config do Hermes:

```yaml
mcp_servers:
  gabi_brain:
    url: http://127.0.0.1:8080/mcp
    headers:
      Authorization: Bearer ${GABI_BRAIN_TOKEN}
    tools:
      include:
      - agenda_financeira
      - agenda_listar
      - avisos_confirmar_entrega
      - avisos_pendentes
      - classificar_lancamento
      - cobranca_rascunho
      - decisao_responder
      - decisoes_abertas
      - documentos_baixar
      - documentos_buscar
      - email_listar
      - fechamento_dia
      - financeiro_contas_a_pagar
      - financeiro_lancamentos
      - financeiro_para_onde_vai
      - financeiro_previsao
      - financeiro_recorrentes
      - financeiro_rumo
      - financeiro_saldo
      - financeiro_vazamentos
      - pedidos_estado
      - pedidos_registrar
      - reembolso_saude_dossie
      - reembolso_saude_pedi
      - reembolso_saude_pendentes
      - reembolso_saude_recebi
      - reembolso_saude_segunda
      - reembolsos_listar
      - reembolsos_preparar_email
      - regras_sugerir
      - resumo_manha
      - tarefas_propor
```
A lista é a **explícita** (sem `*`) e é testada: `tests/mcp/test_hermes.py` falha se ela divergir das ferramentas dos escopos acima. Regerar: `python -m tools.gerar_hermes`.
Se o Streamable HTTP falhar no Hermes, usar `transport: sse` e registrar aqui.

## Rodadas (TC.3)
- Avisos: o Hermes chama `avisos_pendentes`, entrega no Telegram e só então `avisos_confirmar_entrega(aviso_id)` (ler não tira da fila). Aviso já enviado pelo `gabi-brain-telegram` (G15) não volta.
- 07:05: `resumo_manha` (até 5 linhas; a primeira é "⚠ Dados desatualizados…" quando for o caso) e, se quiser mais, `financeiro_contas_a_pagar`.

## Identidade (TC.4): ver `docs/adr/007-identidade-por-remetente.md`
