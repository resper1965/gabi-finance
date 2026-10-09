# ADR-012 — NFS-e, previsão de caixa e Nibo defasado

**Contexto.** O Nibo está defasado: notas vencidas aparecem como em aberto mesmo já recebidas. As NFS-e da Bekaa foram importadas para servir de previsão de entrada.

**Decisão.** A previsão e a projeção nunca somam nota vencida e não baixada; essa fila aparece à parte. O recebimento real é o crédito no extrato casado com a nota pelo valor líquido, como **proposta** (confiança 0,5 + 0,3 se a ≤ 5 dias do vencimento + 0,2 se o tomador aparece no descritivo) que o Ricardo confirma ou rejeita. Nota com recebimento confirmado sai da previsão. Fatura de cartão com mais de 45 dias de atraso não entra na projeção (`DIAS_FATURA_ANTIGA`).

**Consequência.** A previsão é conservadora: subestima entradas até o Ricardo confirmar os recebimentos. Escrita no Nibo continua só pelo lote confirmado (ADR-006).

**Quando reverter.** Quando o Nibo for mantido em dia (baixa automática) ou a confirmação em lote existir e o volume de propostas pedir menos cliques.
