# ADR-009 — Regra de "buraco" e saldo na conferência (calibrada com dado real)

**Estado:** aceita provisoriamente (decisão D1, 09/10/2026; Ricardo pode ajustar os limites).

## Contexto
Na primeira rodada real conferida (09/10/2026, 15 contas liberadas) a conferência reprovava tudo e a faixa do painel nunca ficava verde: cartões sem movimento, contas correntes com um único dia útil vazio e o débito de uma fatura que o banco ainda não publicou como lançamento (diferença de R$ 4.016,63 no Itaú).

## Decisão
1. **Buraco** (`dias_sem_buraco`, só BANK): reprova com **≥ 2 dias úteis seguidos** sem movimento (`MIN_SEGUIDOS`); dia útil isolado passa e fica no `detalhe`. Fim de semana e feriado não interrompem a sequência.
2. **Volume** (`volume_proximo`): não vale para cartão (gasto irregular).
3. **Saldo final** (BANK): a diferença passa se for igual ao total de uma fatura **aberta** ainda sem débito publicado (`contas_pagar.faturas_abertas`); o `detalhe` diz qual fatura.
4. Cartão continua sem conferência de saldo e de buraco.

## Consequência
A rodada passa a ficar `conferida` com dados normais; buracos reais (≥ 2 dias seguidos) e diferenças sem explicação continuam travando o `dados_ate`. Risco aceito: um dia útil isolado sem extrato não trava mais (fica registrado em `conferencia.detalhe`).

## Quando reverter
Se aparecer um extrato com perda de um dia único que ninguém viu: baixar `MIN_SEGUIDOS` para 1 e exigir sync recente (`conta_estado.ult_sync_ok`) como atenuante.
