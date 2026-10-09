# Issue 0001 — Bancos indisponíveis na captura (C6 Bank Empresas e XP Investimentos)

Aberta: 09/10/2026 · Estado: **aberta** · Natureza: dado/seed (conexão no provedor), **não é bug de código**.

## O que acontece
O mcp.ai (Open Finance) devolve `status_conexao` com erro para duas instituições; a captura do gabi.brain registra e segue.

| Instituição | Contas | Sintoma (`conta_estado.status_conexao`, 09/10) |
|---|---|---|
| XP Investimentos | 10 (CREDIT) | "não atualizou em 5 min (última atualização 12/08 12:09 UTC)" — parada há ~2 meses; `ult_sync_ok` nulo |
| C6 Bank Empresas | 11 (CREDIT), 12 (BANK) | "não atualizou em 5 min (última atualização 09/10 06:40 UTC)"; último sync ok 07/10 14:28 BRT; última transação real 07/10 |

## Impacto
- C6 PJ (conta 12) fora do caixa único até reconectar: saldo e lançamentos defasados.
- A conferência da rodada (`conferida`) falha nas contas liberadas sem dados novos (`dias_sem_buraco`/`saldo_final`) e a faixa "sem dados conferidos" pode persistir.
- XP Investimentos: fatura do cartão 10 desatualizada nas faturas abertas.

## Ação (fora do código)
1. Reconectar/renovar o consentimento de C6 Bank Empresas e XP Investimentos no mcp.ai (ação do Ricardo).
2. Depois: rodar `sudo systemctl start gabi-brain-extratos` e conferir `rodada.conferida=1` e `conta_estado.status_conexao`.

## Decisões
- Tratado como **seed**, não desenvolvimento: não bloqueia o app (foco em painel/Fase 1). (Ricardo, 09/10)
- Não alterar a conferência para "perdoar" essas contas; só reavaliar se o provedor seguir indisponível.

## Critério de fechamento
Ambas as instituições com `status_conexao = SUCCESS` e uma rodada de extratos `conferida=1` com as contas 10–12 liberadas.
