# ADR-013 — Aba "Previsão" na área Caixa (desvio do protótipo, R17)

**Contexto.** O protótipo importado não tem uma tela de previsão de caixa; o Ricardo pediu a previsão (entradas e saídas dia a dia) em 09–10/10/2026. R17 pede ADR para qualquer desvio de rótulo ou estrutura do protótipo.

**Decisão.** Nova aba "Previsão" ("Quanto terei em caixa nos próximos dias?") em Caixa, depois de "Resumo", usando as classes do sistema Industry sem estilos novos. A aba "Notas a receber" de Cobrar já existia no protótipo e só passou a ter tela.

**Consequência.** Dois pontos de navegação a mais para as capturas do G14 (aprovação do Ricardo, tela a tela). A previsão nunca soma nota vencida e não baixada (o Nibo é defasado): essa fila aparece à parte.

**Quando reverter.** Se o Ricardo preferir a previsão dentro de "Semanas" ou do Resumo.
