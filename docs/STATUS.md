# gabi.brain · STATUS (retomada rápida)

**Fonte única do que falta:** `docs/BACKLOG.md`. **Decisões que mandam:** `docs/PLANO-DEFINITIVO.md` (só Hermes + gabi.brain; OpenClaw e gabi-fin saem). **Arquitetura em 1 página:** `docs/ARQUITETURA.md`. **Passo a passo de cada fonte:** `docs/runbook.md`.
O histórico detalhado (de 09/10 a 20/10/2026, pacote por pacote) está em `docs/historico/STATUS-ate-2026-10-20.md`: só consulte para saber o que foi feito e quando; não é lista de pendências.

## Estado em 21/10/2026
- **No ar:** dinheiro (extratos 06h/14h, saldos de hora em hora), cobrar, agenda, e-mail (com regras "sempre lixo"), escuta, exames, reembolso de saúde, avisos e Telegram, Hermes (Telegram e WhatsApp).
- **Graph da ness LIGADO em 20/10 (noite):** agenda (5 calendários), e-mail (lixeira desligada), Teams (timer ligado) e contatos (só `resper@ness.com.br`); fontes Google antigas (esper.ws, gmail.com) desligadas; mensagens do Gmail antigo da ness apagadas do banco (backup `antes-apagar-gmail-ness-20261020.db`). Docs: `docs/fontes/graph-ness.md`, runbook `#graph-ness`. ionic espera o administrador do tenant.
- **OpenClaw removido em 20/10:** pacote, `gateway.env`, linha no `gabi.env` e bot do BotFather. A saída do OpenClaw não espera mais o gate H8.
- **Escrita de contatos da ness (na `main`, instalada e `contatos.escrita` LIGADO em 21/10):** fila de propostas com aprovação no painel. Limpeza de contatos (ADR-021: renomear, apagar telefone, apagar contato; estrangeiro deixa de ser inválido) mergeada e instalada em 21/10. ADR-020/021, runbook `#contatos-escrita`.
- **Enriquecer contatos com e-mail (ADR-022):** tipo `adicionar_email` (migração 0074), lote só para ele e piso de interação para `criar`; mergeado na `main` e INSTALADO em 21/10 (sem push). Minors M1-M9 da limpeza corrigidos (84e9546). **Hoje gera 0 propostas:** `contato_google_email` só tem os contatos do Graph da ness (que já têm e-mail no Outlook); os contatos do Google (gmail) não estão no banco porque o sync dá 403 (falta consentimento `contacts.readonly`, G12, passo do dono no navegador). Só entrega valor depois do G12.
- **Release:** tag `v1.0-gabi-brain` criada (F1); C4 aceito.
- **Gate H8:** deixou de ser condição para trabalho novo (o OpenClaw já foi removido, ordem do dono em 21/10). Só resta arquivar o `gabi-fin`, amarrado ao corte G21/D7.
- **Testes:** `.venv/bin/python -m pytest -q` (o `tests/conftest.py` copia um banco-modelo já migrado, então a suíte é rápida). Painel: `cd painel && npx vitest run && npm run build`. Instalar: `sudo ~/instalar-brain.sh`.

## Regras que não mudam
Não mexer em segredos (o Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. R1 a Gabi sugere, o Ricardo decide. R2 nenhum envio externo automático, e e-mail só vai para a lixeira, nunca é apagado de vez. Nada novo no OpenClaw nem no gabi-fin. Cuidado: `pkill -f` mata o próprio shell; use PID guardado.
