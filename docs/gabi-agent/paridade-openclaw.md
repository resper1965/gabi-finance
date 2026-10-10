# Paridade OpenClaw → Hermes/gabi.brain (inventário de 10/10/2026)
Regra do corte (Task 15): nenhuma linha pode ficar em **DECIDIR** ou **MIGRAR** sem fechamento. Status: **OK** (já coberto), **MIGRAR** (recriar como cron do Hermes ou timer), **DECIDIR** (pergunta ao Ricardo), **DESCARTAR** (com motivo).
Fonte: `openclaw cron list` (21 automações), `systemctl` (units `gabi-*`), `/var/lib/gabi/.openclaw` (workspace, skills, scripts, extensões).

## 1. Automações do OpenClaw (21)
| Automação | Quando | O que faz | Destino | Status |
|---|---|---|---|---|
| Heartbeat (main) | 1h | liveness do agente | `gabi-vigia` + `hermes gateway status` | DESCARTAR |
| briefing-matinal | 07:30 | agenda de pagamentos + custos da conta (do `agenda-contas.json`) | `resumo_manha` (brain, 07:05) cobre pagamentos; custos vêm de `financeiro_contas_a_pagar` | MIGRAR (desligar o antigo na virada; um só briefing, Review Focus 4) |
| Resumo Diário de E-mails | 08:00 | resumo de e-mails | Trabalho do brain (Fase 3 congelada) ou triagem-email | DECIDIR (Task 8) |
| Alerta de Pagamentos Diários | 09:00 | alerta de vencimentos/atraso/débito ausente | financeiro novo (branch `feat/financeiro-conciliacao`) + avisos do brain (`vence_hoje`, `conta_atrasada`) | OK após Task 6 |
| Resumo Semanal de Pagamentos | dom 10:00 | agenda da semana + previsão 30 dias | aba Previsão do brain (ADR-013) + cron Hermes | MIGRAR |
| forecast-semanal | seg 08:00 | previsão de caixa por semana, dia mais baixo, semana negativa (Sonnet 5.5; **com erro 2×**) | `financeiro_*` + Previsão do brain; cron Hermes | MIGRAR (corrigir erro antes) |
| promessas-diario | 20:00 | revisa `operacao/promessas.md`, cartões na fila de decisões | cron Hermes lendo o arquivo (ou tabela no brain) | DECIDIR |
| fechamento-noturno | 21:00 | `gabi_evening_wrapup.py` + gastos do dia e baixas | `financeiro_lancamentos` do dia + wrapup | MIGRAR |
| sanidade-automacoes | 06:00 | `verificar_automacoes.py` (confere as próprias rotinas) | `gabi-vigia` (substitui) | DESCARTAR após vigia cobrir Hermes (Task 10) |
| continuidade | 10:00 | **dead-man switch**: 3–4 dias sem mensagem → pergunta ao Boss; ≥5 dias → manda texto de continuidade a Louise e Giovanna por WhatsApp | exige WhatsApp do Hermes e é envio externo automático (**R2**) | DECIDIR — não pode perder em silêncio |
| validades-semanal | seg 08:30 | documentos da família que vencem em 180 dias | Paperless/`documentos_buscar` + cron Hermes | MIGRAR |
| teams-copilot | */15 8–20h seg–sex | copiloto Teams (`gabi_teams_copilot.py`), sem externos | Fase 3 (Trabalho, congelada) | DECIDIR |
| Auto-limpeza e-mails | 1h | limpeza de e-mails (sessão WhatsApp do pessoal) | triagem-email (branch) | DECIDIR (Task 8) |
| limpeza-emails-github | (command) | `github_email_cleanup.py` | rotina sem modelo; timer próprio | MIGRAR |
| Skill collection review ×2 | 7d | revisão de skills (main, escuta) | `hermes curator` | DESCARTAR |
| Alerta fatura Amex (dia 28) | mensal | lembrete de fatura | aviso do brain (`vence_hoje`) | OK |
| por-onde-vazou | dia 1 | relatório mensal (Raio-X) | Raio-X mensal (Task 8) | DECIDIR |
| Aniversários (Benedita, Cookie, Chafic, Sandra) e lembrete-passaporte (17/09/2027) | anual | lembretes | recriar como `hermes cron create` (um por data) | MIGRAR |

## 2. Units e timers fora do gateway (independem do OpenClaw)
`gabi-brain-*` (api, mcp, fontes, saldos, extratos, notas, comprovantes, trabalho, avisos, telegram, backup, exportação), `gabi-financeiro`, `gabi-fluxos-diario/mensal`, `gabi-drive`, `gabi-backup`, `gabi-vigia`, `gabi-guarda-sessoes`, `gabi-reembolso(.path/-segunda)`, `gabi-wa-docs.path`. **Status: OK**, exceto os que chamam o gateway do OpenClaw — a verificar linha a linha (Task 9 passo 2): `gabi-reembolso*` (fila `fila-reembolso`, escuta), `gabi-wa-docs.path` (PDF recebido no WhatsApp → Paperless), `gabi-guarda-sessoes` e `gabi-vigia` (vigiam sessões e gateway do OpenClaw).

**Resultado da verificação (10/10, `ExecStart` e `Path*` das units):**
| Unit | Dependência do OpenClaw | Ação no corte |
|---|---|---|
| `gabi-vigia` (`vigia_gateway.py`) | vigia o gateway do OpenClaw | trocar o alvo para `hermes-gateway` **antes** de desligar, senão alerta "gateway parado" para sempre (Task 10) |
| `gabi-guarda-sessoes` (`sessoes.py`) | sessões do OpenClaw | descartar no corte (Hermes tem `sessions/` próprio) |
| `gabi-wa-docs.path` | observa `.openclaw/media/inbound` e `workspace/media/inbound` (PDF/foto recebido no WhatsApp → Paperless) | apontar para o diretório de mídia do Hermes (`~/.hermes/image_cache` e documentos) ou DECIDIR descartar |
| `gabi-reembolso.path` | observa `.openclaw/fila-reembolso` (escrita pelo agente `escuta`) | DECIDIR junto com o agente `escuta` |
| `gabi-financeiro`, `gabi-fluxos-*`, `gabi-contas-cartoes`, `gabi-reembolso-segunda` | só usam `HOME`/dados do usuário `gabi`; enviam ao Telegram pelo token do OpenClaw (`TELEGRAM_BOSS`, `financeiro.env`) | OK, mas o token usado para enviar muda se o bot do OpenClaw sair (Task 15 passo extra) |

## 3. Canais e agentes
| Item | Hoje | No Hermes | Status |
|---|---|---|---|
| Telegram do Boss | OpenClaw (bot atual, token em store write-only) | bot novo (Task 12) | MIGRAR (por último) |
| WhatsApp do Boss | OpenClaw (+5511983397196) | número dedicado (Task 13) | MIGRAR (por último) |
| Agente `escuta` (WhatsApp pessoal: reembolso, pistas) | OpenClaw, 2 agentes | sem equivalente | DECIDIR (escopo de ADR-007: só o Ricardo conversa) |
| Plugin `gabi-silencio` (barra narração) | OpenClaw | Hermes tem `SOUL.md`; sem plugin | DECIDIR (medir ruído no Hermes) |
| `modelByChannel`, `modelPolicy` | OpenClaw | `config.yaml` do Hermes | MIGRAR (DeepSeek flash padrão; Sonnet 5.5 só no forecast) |

## 4. Conhecimento e arquivos do workspace (`/var/lib/gabi/.openclaw/workspace`)
`SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `PENDING.md`, `TODO.md`, `AGENTS.md`; pastas `financas/` (agenda, contatos), `operacao/` (promessas, validades), `continuidade/`, `custodia/`, `marcela/`, `contas-entrada/`, `docs/`; skills `agenda-financeira`, `documentos`, `financas`, `operacao`, e em `skills/`: `fechamento-noturno`, `teams-copilot`, `github`, `native-linear`, `traffic-alert`, `fill-brotas-forms`, `composio-connect`. Scripts em `.openclaw/scripts` (OCR, PDF, m365, emissores, planilha_compromissos, reembolso…).
- **Status:** DECIDIR por pasta. Proposta: dados financeiros já vivem no brain (não migrar); `USER.md`/`MEMORY.md`/`IDENTITY.md` → importar para `~/.hermes/memories` (resumo, não cópia cega); `continuidade/`, `custodia/`, `marcela/` → decisão do Ricardo antes de qualquer cópia (conteúdo sensível); scripts continuam sob o usuário `gabi` e são chamados por timer, não pelo gateway.
- Tamanho do diretório: 5,4 GB (sessões e backups); o backup do corte exporta só config, workspace e agentes.
