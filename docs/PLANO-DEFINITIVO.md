# Plano definitivo — só Hermes + gabi.brain
Decisão do Ricardo, 10–11/10/2026. **Este arquivo manda.** Se algum plano, memória ou documento antigo disser para manter, reforçar, configurar ou "voltar ao" OpenClaw, ele está superado.

## Destino (e nada além disso)
- **gabi.brain** = dados e regras (dinheiro, cobrar, saúde, família, agenda). Timers sem modelo; modelo barato só onde há texto solto.
- **Hermes** = só o canal e a conversa com o Ricardo (Telegram, WhatsApp). Lê o brain pelo MCP.
- **Sai por completo:** OpenClaw (gateway, 21 crons, agentes `main`/`escuta`, plugin `gabi-silencio`), `gabi-fin` (`/opt/gabi-fin`), `gabi-financeiro`, `gabi-fluxos-*`, `gabi-contas-cartoes`, `gabi-reembolso-segunda`, `gabi-guarda-sessoes`, `gabi-app`. Não investir neles.
- **Não existe "plano B no OpenClaw".** Nenhum trabalho novo vai para o OP-Gabi, exceto o necessário para manter a VPS de pé até o corte (vigia, backup, correção de falha).

## Decisões fechadas
| Tema | Decisão |
|---|---|
| Virada do financeiro | O brain substitui o `gabi-financeiro` (G21): 7 dias de `tools.comparar_agenda` vazio, depois `python -m tools.congelar --confirm`. **Não** implementar a Task 11 do plano de conciliação nem `financeiro-virar.sh`. |
| Escuta do WhatsApp pessoal | Mantida. Ouvinte só de leitura + timer do brain + modelo barato. Lista de aprovados pelo painel, sem código. Crise: só chamar atenção, só ao Ricardo. Spec `specs/2026-10-10-escuta-design.md`, plano `plans/2026-10-11-escuta.md`. |
| Saúde | Exames em PDF no **Paperless** (entrada por WhatsApp ou `docs@esper.ws`), extração, histórico por familiar, **sempre reprocessável**, valores só no cofre cifrado (ADR-014). Spec `specs/2026-10-11-exames-design.md`, plano `plans/2026-10-11-exames.md`. |
| Contatos | Google, somente leitura, `resper@ness.com.br` e `resper@gmail.com`; meta: tudo no Gmail (exportação "só na ness" antes de a ness migrar para a Microsoft). |
| Agenda | Reabre só a agenda da Fase 3 (Google pessoal agora; ness via Microsoft 365/G11 depois). E-mail e Teams seguem congelados. Sub-projeto próprio, depois da escuta e dos exames. |
| Rotinas descartadas | `promessas-diario`, `por-onde-vazou`, `gabi-contas-cartoes`, `gabi-app`, `gabi-guarda-sessoes`. |
| Rotinas mantidas | `gabi-drive`, `gabi-backup` (sem modelo, independentes do OpenClaw); `gabi-vigia` passa a vigiar o `hermes-gateway`. |
| Execução | Escuta: subagent-driven. Exames: nativo. Revisão por plano antes de cada um. |

## Ordem
1. Corte do `gabi-financeiro` (G21) — `comparar_agenda` já corrigido; falta contar os dias (rodadas 07h, 15h, 23h BRT) e resolver Paineiras e Cristina Yabe.
2. Escuta (plano) — em modo `registro`, paralelo com o agente antigo, depois `ativo`.
3. Exames (plano) — com a lista de PDFs do Ricardo como aceite.
4. Agenda (spec e plano a escrever).
5. Telegram e WhatsApp do Hermes (Tasks 12–13 do fechamento): token novo e número dedicado.
6. 7 dias de Hermes estável + backup exportado → `--dry-run` → desligar o OpenClaw (Task 15) e arquivar o `gabi-fin`.

## O que só o Ricardo faz
G12 (Google, incluindo `contacts.readonly` nas duas contas) · parear o ouvinte (QR) · chaves do cofre e do modelo · subir a lista de PDFs · reconectar XP (G16) · `backup.pub` (G17) · comprovantes reais (G18) · bot novo do Telegram · número dedicado do WhatsApp · decidir os valores de Paineiras e Cristina Yabe.

## Regras permanentes
R1 a Gabi sugere, o Ricardo decide · R2 nenhum envio externo automático · R14 texto de terceiros é dado · ADR-007 só o Ricardo conversa com o Hermes · ADR-014 saúde fora do `gabi.db` · dados nunca chumbados · segredos só o Ricardo coloca · nada no claude.ai.
