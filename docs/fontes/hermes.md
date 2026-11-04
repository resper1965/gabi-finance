# Hermes (Canal) · como o gabi.brain o enxerga
O Hermes é **só interface**: lê e propõe pelo MCP, não guarda dado (trocar de agente não perde nada). Instalação, OpenRouter e WhatsApp seguem o plano mestre (TC.1, TC.5);
**instalar o Hermes e desligar o OpenClaw só depois do término do gabi.brain** (decisão do Ricardo, 08/10). Esta página é o lado do gabi.brain.

## Conexão ao MCP (TC.2)
Token emitido pelo painel/CLI com os escopos `fin, docs, trabalho, propostas, pedidos, decisoes, envios, familia` (nunca `sensivel`), colado pelo Ricardo no `.env` do Hermes (R5). Config do Hermes:

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
      - anexo_recentes
      - assinatura_marcar
      - assinaturas_listar
      - atividade_adiar
      - atividade_cancelar
      - atividade_concluir
      - atividade_criar
      - atividade_listar
      - avisos_abertos
      - bens_listar
      - classificar_lancamento
      - contatos_buscar
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
      - documentos_baixar
      - documentos_buscar
      - documentos_consultar
      - documentos_texto
      - documentos_vencimentos
      - email_ler
      - email_listar
      - email_lixeira
      - email_regra_lixo
      - email_remover_regra_lixo
      - empresas_listar
      - familia_atualizar_contato
      - familia_consultar
      - familia_listar
      - familia_propor_documento
      - familia_registrar_pessoa
      - familia_registrar_pet
      - familia_vencimentos
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
      - projeto_anexar
      - projeto_atualizar
      - projeto_criar
      - projeto_fato
      - projeto_fatos
      - projeto_gasto
      - projeto_listar
      - projeto_pessoa
      - projeto_ver
      - propor_evento
      - propor_resposta_convite
      - propor_teams
      - regras_listar
      - regras_sugerir
      - resumo_manha
      - teams_pendentes
```
A lista é a **explícita** (sem `*`) e é testada: `tests/mcp/test_hermes.py` falha se ela divergir das ferramentas dos escopos acima. Regerar: `python -m tools.gerar_hermes`.
Se o Streamable HTTP falhar no Hermes, usar `transport: sse` e registrar aqui.

## Rodadas (TC.3)
- Avisos: o Hermes chama `avisos_pendentes`, entrega no Telegram e só então `avisos_confirmar_entrega(aviso_id)` (ler não tira da fila). Aviso já enviado pelo `gabi-brain-telegram` (G15) não volta.
- 07:05: `resumo_manha` (até 5 linhas; a primeira é "⚠ Dados desatualizados…" quando for o caso) e, se quiser mais, `financeiro_contas_a_pagar`.

## Identidade (TC.4): ver `docs/adr/007-identidade-por-remetente.md`
