# gabi.brain · STATUS (retomada rápida)

**Fonte única do que falta:** `docs/BACKLOG.md`. **Decisões que mandam:** `docs/PLANO-DEFINITIVO.md` (só Hermes + gabi.brain; OpenClaw e gabi-fin saem) e `docs/adr/023-simplificacao.md` (o que foi cortado e por quê). **Arquitetura em 1 página:** `docs/ARQUITETURA.md`. **Passo a passo de cada fonte:** `docs/runbook.md`.
O histórico detalhado (09/10 a 21/10/2026) está em `docs/historico/`: só consulte para saber o que foi feito e quando; não é lista de pendências.

## Estado em 22/10/2026
- **Simplificação (ADR-023) na branch `feat/simplificacao`, ainda NÃO instalada:** saem a escuta do WhatsApp, a saúde, o módulo Trabalho, a cobrança e o reembolso PJ (troca por `despesas_por_empresa`), ferramentas MCP sem uso (ficam 18) e 26 tabelas vazias (migração 0075). "Para quem" certeiro passa a ser aplicado sozinho (≥2 decisões iguais do Ricardo); a conferência de saldo só informa (aviso `saldo_divergente`). Instalar é o item SP1 do BACKLOG.
- **No ar (produção, antes da simplificação):** dinheiro (extratos e saldos), a receber, agenda, e-mail (com regras "sempre lixo"), Teams, contatos da ness, avisos e Telegram, Hermes (Telegram e WhatsApp). Escuta, exames e reembolso de saúde estão desligados.
- **Graph da ness ligado desde 20/10:** agenda, e-mail (lixeira desligada), Teams e contatos (`resper@ness.com.br`). ionic espera o administrador do tenant. Google contatos, ionic e Nibo em espera por chave (não alertar).
- **Conferência de extratos:** em 21/10 a correção do `saldo_final` foi instalada e a rodada 3527 saiu `conferida=1`. Com a ADR-023 a conferência deixa de travar.
- **Release:** tag `v1.0-gabi-brain` no GitHub.
- **Testes:** `.venv/bin/python -m pytest -q` (o `tests/conftest.py` copia um banco-modelo já migrado). Painel: `cd painel && npx vitest run && npm run build`. Instalar: `sudo ~/instalar-brain.sh`.

## Regras que não mudam
Não mexer em segredos (o Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. R1 a Gabi sugere, o Ricardo decide (exceção: "para quem" certeiro). R2 nenhum envio externo automático, e e-mail só vai para a lixeira, nunca é apagado de vez. Nada novo no OpenClaw nem no gabi-fin. Pergunta vai para o Hermes; tela só para decidir ou revisar; nada vira sistema antes de um mês de uso manual. Cuidado: `pkill -f` mata o próprio shell; use PID guardado.
