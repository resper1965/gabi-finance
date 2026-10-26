# ADR-030 · Quem gastou (portador do cartão), separado de para quem foi

Data: 26/10/2026 · Estado: aceito · Spec: `docs/superpowers/specs/2026-10-26-gastadores-design.md` · Plano: `docs/superpowers/plans/2026-10-26-gastadores.md`

**Contexto.** Em Gastos, "por pessoa" misturava quem passou o cartão com de quem é o gasto, e qualquer pessoa cadastrada podia aparecer. Os cartões são todos do Ricardo e os portadores são ele, Louise, Giovanna e Sabrina. O Open Finance não diz qual cartão físico (titular ou adicional) fez a compra.

**Decisões (Ricardo, 26/10).**
1. Gastador = portador da conta (`conta.usuarios`). Pessoa sem cartão nunca é gastadora.
2. Nos compartilhados, "eu indico": nada é deduzido do histórico nem do "para quem". O histórico fica "a indicar".
3. "Quem gastou" é separado de "para quem foi".
4. O Hermes grava depois de mostrar e ouvir o sim.

**Como ficou.**
- Migração 0084: `lancamento.gastador_id`, `lancamento.gastador_origem` ('cartao' | 'voce' | 'regra') e `gastador_regra` ("sempre assim" por loja **naquele** cartão).
- `gabi/dinheiro/gastador.py`: cartão de um portador e conta corrente se preenchem sozinhos. A indicação 'voce' nunca é sobrescrita. Cartão que passa de 1 para 2 portadores volta a "a indicar". Rodado ao fim da captura, na mesma etapa do não-é-gasto.
- API: `gastador_id` no PATCH e no lote (só portador daquela conta; 400 `nao_portador` e nada gravado), `pendente=gastador`, filtro `gastador`, `destino/agrupado?por=gastador`. O contador do menu Gastos soma as compras a indicar **do mês corrente**: o histórico tinha cerca de 2.750 e fica no filtro da tela.
- Painel: em Lançamentos, filtro "Quem gastou: a indicar" com botões só dos portadores e "sempre <pessoa> em <loja> neste cartão". Em Cartões, coluna e lote. Em Para onde vai, as vistas "Quem gastou" e "Para quem foi".
- MCP: `financeiro_indicar_gastador`; `financeiro_lancamentos` com `gastador` e `pendente`; `financeiro_para_onde_vai(por="gastador")`.
- Junto, uma correção da ADR-029: o cartão "Assinaturas por mês" do Caixa › Resumo passou a usar o mesmo rol da tela de Assinaturas. Antes, ignorava o status e o filtro de hábito, e "a conferir" nunca zerava.

**Fora.** Ler a fatura em PDF para achar o adicional; sugestão por histórico; mudar "para quem".

**Desfazer.** Ver o cabeçalho de `migrations/0084_gastador.sql`. Depois, `git revert` do merge e reinstalar. No Hermes, restaurar config e SOUL dos backups, reiniciar e dar `/new`.
