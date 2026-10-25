# gabi.brain · BACKLOG (fonte única do que falta)
**Este arquivo manda sobre o que falta.** `STATUS.md` é a retomada rápida; `PLANO-DEFINITIVO.md` guarda as decisões; `/home/ricardo/PENDENCIAS-RICARDO.md` aponta para cá.
Reescrito em 22/10/2026 depois da simplificação (ADR-023): só o que segue aberto. O backlog anterior, com o histórico de cada item fechado, está em `docs/historico/BACKLOG-ate-2026-10-21.md`.

Legenda: dono **R** = Ricardo · **C** = Claude · **R+C** = juntos. Status: 🔧 em curso · ⛔ bloqueado · ⏸ em espera · ❓ a verificar.
Regras que valem em tudo: R1 a Gabi sugere, o Ricardo decide (exceção: "para quem" certeiro, ADR-023) · R2 nenhum envio externo automático · segredos só o Ricardo coloca · dados nunca chumbados · nada no claude.ai · esquema novo = migração 0076+.
**Regra para o que vier (ADR-023):** pergunta vai para o Hermes (MCP); o painel só ganha tela quando há decisão ou lista para revisar; nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual que mostre a necessidade.

## Em espera por chave de terceiros (ordem do dono, 21/10)
Google (contatos G12), Graph da ionic, Nibo (A7/C3) e Tailscale da família (G13) aguardam chave ou consentimento. **Não alertar, não cobrar e não propor ações sobre eles até o Ricardo dizer que estamos liberados.** `gabi-brain-notas.timer` está desligado (religar: `sudo systemctl enable --now gabi-brain-notas.timer`).

## Aberto
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| AT1 | Marcar agenda e responder no Teams com anuência do Ricardo (ADR-024) | R | 🔧 mergeado (PR #2) e instalado em 22/10, migração 0076 aplicada, `envios.escrita` desligado; faltam os passos do dono no runbook `#envios` | passos do dono feitos e um envio real conferido |
| A2 | Uma semana de aceite: conferir telas Agenda, Prioridades e "Na lixeira" contra o app do Google | R | 🔧 | semana sem erro anotada |
| A7 | Nibo: renovar `NIBO_TOKEN` (401 desde 16/10) | R | ⏸ on hold (chave da Nibo) | `systemctl start gabi-brain-notas` sem erro |
| C3 | Conferir `NIBO_TOKEN` e as rotas `/partners`, `/customers`, `/categories` com dado real | R+C | ⏸ on hold (chave da Nibo) | G8 fechado |
| DOC1 | Documentos (ADR-027): instalar (`sudo ~/instalar-documentos.sh`: backup de `~/.hermes/config.yaml` em `config.yaml.bak-antes-documentos`, acrescenta `documentos_consultar`, `documentos_vencimentos` e `bens_listar` no `include` do `gabi_brain`, instala o SOUL e reinicia o `hermes-gateway`), `/new` no Telegram e no WhatsApp, aprovar as primeiras propostas na aba Documentos | R | 🔧 pronto na branch `feat/documentos`, a instalar; passos em `docs/runbook.md#documentos` | primeira rodada lida, propostas aprovadas e o Hermes responde um número com o link |
| H7 | 7 dias de Hermes estável + backup exportado | R+C | ⛔ depende de H5 (número dedicado, lista do Ricardo) | sem queda em 7 dias |

## Decisões do Ricardo sem resposta
(nenhuma)

## Decididas em 22/10
- **Extratos:** continuam 2x por dia (06h e 14h).
- **Marcação de agenda e resposta no Teams com anuência:** SIM. Item AT1 em "Aberto"; exige ADR de exceção à R2 (nada sai sem o OK explícito do Ricardo em cada envio).
- **Tailscale da família (G13):** on hold; não alertar nem propor até o Ricardo liberar.
- **A6 (custo do modelo de reserva do e-mail):** não importa por ora; não alertar.
- **Resumo da manhã pós-ADR-023:** chegou pelo Hermes (conferido pelo Ricardo).
- **SP2:** apagados ouvinte da escuta (`/opt` e `/var/lib/escuta-ouvinte`), cofre `saude.enc` e as chaves (`/etc/gabi/saude.key`, `~/saude.key.COPIE-E-APAGUE`). Aparelho do WhatsApp: o Ricardo desconecta.

## Depois (sugeridos na revisão de 21/10, não escolhidos ainda)
- Enxugar a lixeira do e-mail (8 condições, conferência ao vivo, 8 tentativas) para regras de remetente.
- Congelar a rodada diária de propostas de contatos (ADR-022 gera 0 propostas até o G12).
- Tirar do alerta "emergencial" os e-mails do próprio sistema (falhas do ness.brain, Google Cloud).
- Reduzir a frequência dos timers de Teams (5 min) e agenda (15 min).
- Microsoft Graph da ionic (G11): parado pelo administrador do tenant (`docs/fontes/graph-ionic-passo-a-passo.md`).
- Agenda financeira diária sem LLM (cron `no_agent` do Hermes, como a semanal).
- Documentos que coexistem (apólice, contrato, outro): um mais novo do mesmo titular e tipo fecha o aviso de vencimento do outro (ADR-027).

## Cortado em 22/10 (ADR-023)
Escuta do WhatsApp (E1–E4), saúde (S1–S3, D8), módulo Trabalho (Frentes, Tarefas, Entregas/Linear, contatos em aberto), cobrança e reembolso PJ (C1, C2, AR2, comprovantes, pedidos), Obsidian por pessoa, perfil de normalidade (PF1), tela Configuração, 7 abas vazias do menu Gabi, ferramentas MCP sem uso (o Hermes fica com 18), índice FTS da memória. D2 (conferência travando o `dados_ate`) resolvido: a conferência só informa.

## Obsoleto (não fazer)
- **G16** reconectar XP Investimentos: a conexão saiu do mcp.ai em 11/10.
- Qualquer "plano B" no OpenClaw; trabalho novo no `gabi-fin`, `gabi-app`, `gabi-fluxos-*`, `gabi-contas-cartoes`, `gabi-guarda-sessoes`.
- Juntar correio, agenda e Teams num timer só (acopla falhas e quebra o aviso `servico_falhou`).

## Como manter
Ao fechar um item, tire-o daqui e registre a evidência (comando, número, commit) no commit ou em `STATUS.md`. Item novo entra em "Aberto" com dono, ou em "Depois" se não tem pressa.
