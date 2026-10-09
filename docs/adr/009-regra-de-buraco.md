# ADR-009 — Regra de "buraco" e saldo na conferência (calibrada com dado real)

**Estado:** aceita provisoriamente (decisão D1, 09/10/2026; Ricardo pode ajustar os limites).

## Contexto
Na primeira rodada real conferida (09/10/2026, 15 contas liberadas) a conferência reprovava tudo e a faixa do painel nunca ficava verde: cartões sem movimento, contas correntes com um único dia útil vazio e o débito de uma fatura que o banco ainda não publicou como lançamento (diferença de R$ 4.016,63 no Itaú).

## Decisão
1. **Buraco** (`dias_sem_buraco`, só BANK): reprova com **≥ 2 dias úteis seguidos** sem movimento (`MIN_SEGUIDOS`); dia útil isolado passa e fica no `detalhe`. Fim de semana e feriado não interrompem a sequência.
2. **Volume** (`volume_proximo`): não vale para cartão (gasto irregular).
3. **Saldo final** (BANK): a diferença passa se for igual ao total de uma fatura **aberta** ainda sem débito publicado (`contas_pagar.faturas_abertas`); o `detalhe` diz qual fatura.
4. Cartão continua sem conferência de saldo e de buraco.
5. **Saldo final** (BANK): a diferença também passa se for igual à soma dos lançamentos **pendentes** da janela (o banco já abateu o pendente do saldo; evidência real 09/10: débito automático do cartão Pão de Açúcar, R$ 4.016,63, pendente).

6. **Revisão 09/10/2026 (noite) — conta de movimento irregular.** O C6 PJ (conta 12) reprovava por 28 e 29/09 sem movimento; nos últimos 56 dias úteis ele teve movimento em 64% dos dias (Itaú conta 6: 56%) e sequências de 2 e até 3 dias úteis vazios são rotina. Se a fração de dias úteis com movimento no histórico é **< 75%** (`DENSIDADE_REGULAR`), o buraco só reprova com **≥ 4 dias úteis seguidos** (`MIN_SEGUIDOS_IRREGULAR`); contas regulares seguem com 2. Decisão do Ricardo: "c6 não movimenta muito, é normal". Obs.: a conferência de `saldo_final` compara só o último dia com o anterior; ela **não** prova que dias antigos estavam vazios, por isso o critério é o perfil da conta, não o saldo.

## Consequência
A rodada passa a ficar `conferida` com dados normais; buracos reais (≥ 2 dias seguidos) e diferenças sem explicação continuam travando o `dados_ate`. Risco aceito: um dia útil isolado sem extrato não trava mais (fica registrado em `conferencia.detalhe`).

## Quando reverter
Para contas irregulares, se uma perda de 2–3 dias passar despercebida: baixar `MIN_SEGUIDOS_IRREGULAR` para 3.
Se aparecer um extrato com perda de um dia único que ninguém viu: baixar `MIN_SEGUIDOS` para 1 e exigir sync recente (`conta_estado.ult_sync_ok`) como atenuante.
