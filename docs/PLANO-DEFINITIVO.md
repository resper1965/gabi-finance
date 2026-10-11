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
| Agenda | **Código completo (11/10, ADR-017):** Google (gmail, ness, bekaa, backoffice@bekaa.eu), somente leitura, pela ponte, em horário de Brasília; resumo da manhã, `agenda_listar` (Hermes), painel e conflitos leem o brain. ionic e a ness (Microsoft) entram por Graph depois do G11. Marcação com anuência (escrita: exceção controlada à R2) e Teams são projetos seguintes, cada um com spec e plano. Spec `specs/2026-10-11-agenda-design.md`, plano `plans/2026-10-11-agenda.md`. |
| Valores divergentes (11/10) | **Paineiras R$2.793 e Cristina Yabe R$370: o brain está certo**; o financeiro antigo estava errado nessas duas linhas. No G21 essas duas divergências já conhecidas não bloqueiam o corte. |
| E-mail | **Código completo (11/10, ADR-018):** Google (gmail, ness, bekaa, backoffice), a Gabi lê, prioriza, manda o obviamente inútil para a **lixeira** (restaurável por 30 dias; nunca apaga de vez) e alerta as emergências no Telegram e no WhatsApp. Começa já movendo (decisão do Ricardo), com seis condições juntas, limiar alto e resumo diário. ionic/ness por Graph = G11. Spec `specs/2026-10-11-email-design.md`, plano `plans/2026-10-11-email.md`. |
| Rotinas descartadas | `promessas-diario`, `por-onde-vazou`, `gabi-contas-cartoes`, `gabi-app`, `gabi-guarda-sessoes`. |
| Rotinas mantidas | `gabi-drive`, `gabi-backup` (sem modelo, independentes do OpenClaw); `gabi-vigia` passa a vigiar o `hermes-gateway`. |
| Execução | Escuta: subagent-driven. Exames: nativo. Revisão por plano antes de cada um. |

## Ordem
1. Corte do `gabi-financeiro` (G21) — `comparar_agenda` já corrigido; falta contar os dias (rodadas 07h, 15h, 23h BRT) (Paineiras e Cristina Yabe já decididas: vale o brain).
2. Escuta — **código completo (11/10, ADR-016)**; aguardando passos do Ricardo: parear, G12, chave com limite, ligar em `registro`, comparar por N dias (`tools.comparar_escuta`), `ativo`. Runbook `#escuta-paralelo`.
   - **ABERTO — reembolso de saúde (`reembolso_fila.py`/`reembolso_segunda`) ainda no gabi-fin:** precisa de porte para o brain antes de desligar o gabi-fin (spec da escuta §3.6, desvio registrado no ADR-016). Até lá `gabi-reembolso.path` e `gabi-reembolso-segunda` NÃO são aposentados com a escuta. Atenção: depois que o agente `escuta` sair, a `fila-reembolso` deixa de receber pistas novas do WhatsApp; o porte precisa decidir de onde elas passam a vir.
3. Exames (plano) — com a lista de PDFs do Ricardo como aceite.
4. Agenda — **código completo (11/10, ADR-017)**; aguardando passos do Ricardo: consentimento OAuth de cada conta (`calendar.readonly` + `contacts.readonly`), `/etc/gabi/google.env`, liberar calendários no painel, `agenda_listar` no include do Hermes, ligar `gabi-brain-agenda.timer`, aceite da semana. Runbook `#agenda`. Depois: ionic/ness por Graph (G11), e-mail mínimo, marcação com anuência, Teams.
5. E-mail — **código completo (11/10, ADR-018)**; aguardando passos do Ricardo: consentimento OAuth das contas com `gmail.modify`, `/etc/gabi/google.env`, chave do modelo com limite, cadastrar e liberar contas, critérios e VIPs, `email_listar` no include do Hermes, ligar `gabi-brain-correio.timer`, aceite da semana, só então ligar a lixeira. Runbook `#correio`.
6. Telegram e WhatsApp do Hermes (Tasks 12–13 do fechamento): token novo e número dedicado.
7. 7 dias de Hermes estável + backup exportado → `--dry-run` → desligar o OpenClaw (Task 15) e arquivar o `gabi-fin`. Gate: em registro a crise é só registrada, sem aviso; NÃO desligue o OpenClaw antes de escuta.modo='ativo'.

## O que só o Ricardo faz
G12 (Google, incluindo `contacts.readonly` nas duas contas) · parear o ouvinte (QR) · chaves do cofre e do modelo · subir a lista de PDFs · reconectar XP (G16) · `backup.pub` (G17) · comprovantes reais (G18) · bot novo do Telegram · número dedicado do WhatsApp.

## Regras permanentes
R1 a Gabi sugere, o Ricardo decide · R2 nenhum envio externo automático · R14 texto de terceiros é dado · ADR-007 só o Ricardo conversa com o Hermes · ADR-014 saúde fora do `gabi.db` · dados nunca chumbados · segredos só o Ricardo coloca · nada no claude.ai.
