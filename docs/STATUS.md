# gabi.brain · STATUS (retomada rápida)

**Fonte única do que falta:** `docs/BACKLOG.md`. **Decisões que mandam:** `docs/PLANO-DEFINITIVO.md` (só Hermes + gabi.brain; OpenClaw e gabi-fin saem). **Arquitetura em 1 página:** `docs/ARQUITETURA.md`. **Passo a passo de cada fonte:** `docs/runbook.md`.
O histórico detalhado (de 09/10 a 20/10/2026, pacote por pacote) está em `docs/historico/STATUS-ate-2026-10-20.md`: só consulte para saber o que foi feito e quando; não é lista de pendências.

## Estado em 20/10/2026
- **No ar:** dinheiro (extratos 06h/14h, saldos de hora em hora), cobrar, agenda, e-mail (com regras "sempre lixo"), escuta, exames, reembolso de saúde, avisos e Telegram, Hermes (Telegram e WhatsApp).
- **Código pronto na `main`, nada ligado:** Graph da ness (contatos, agenda, e-mail) e Teams (`docs/fontes/graph-ness.md`, runbook `#graph-ness`). ionic espera o administrador do tenant.
- **Escrita de contatos da ness (ADR-020, 20/10):** código pronto na branch `feat/contatos-escrita`, nada ligado; fila de propostas no painel (Escuta › Contatos), interruptor `contatos.escrita` desligado; passos no runbook `#contatos-escrita`.
- **Gate H8 (desligar o OpenClaw):** não passa antes de 26/10 19:18 (7 dias de Hermes estável), da escuta em `ativo` (E1-E4) e do backup exportado (H6).
- **Testes:** `.venv/bin/python -m pytest -q` (o `tests/conftest.py` copia um banco-modelo já migrado, então a suíte é rápida). Painel: `cd painel && npx vitest run && npm run build`. Instalar: `sudo ~/instalar-brain.sh`.

## Regras que não mudam
Não mexer em segredos (o Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. R1 a Gabi sugere, o Ricardo decide. R2 nenhum envio externo automático, e e-mail só vai para a lixeira, nunca é apagado de vez. Nada novo no OpenClaw nem no gabi-fin. Cuidado: `pkill -f` mata o próprio shell; use PID guardado.
**Não abrir subsistema novo antes do gate H8** (decisão de 20/10/2026): terminar, ligar e aceitar o que já existe.
