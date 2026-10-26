# gabi.brain · BACKLOG (fonte única do que falta)
**Este arquivo manda sobre o que falta.** `STATUS.md` é a retomada rápida; `PLANO-DEFINITIVO.md` guarda as decisões; `/home/ricardo/PENDENCIAS-RICARDO.md` aponta para cá.
Reescrito em 22/10/2026 depois da simplificação (ADR-023): só o que segue aberto. O backlog anterior, com o histórico de cada item fechado, está em `docs/historico/BACKLOG-ate-2026-10-21.md`.

Legenda: dono **R** = Ricardo · **C** = Claude · **R+C** = juntos. Status: 🔧 em curso · ⛔ bloqueado · ⏸ em espera · ❓ a verificar.
Regras que valem em tudo: R1 a Gabi sugere, o Ricardo decide (exceção: "para quem" certeiro, ADR-023) · R2 nenhum envio externo automático · segredos só o Ricardo coloca · dados nunca chumbados · nada no claude.ai · esquema novo = migração 0076+.
**Regra para o que vier (ADR-023):** pergunta vai para o Hermes (MCP); o painel só ganha tela quando há decisão ou lista para revisar; nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual que mostre a necessidade.

## Em espera por chave de terceiros (ordem do dono, 21/10)
**26/10: Google (G12, 4 contas) e Tailscale da família (G13) liberados pelo Ricardo** (itens GO1 e G13 em "Aberto"). Graph da ionic e Nibo (A7/C3) seguem aguardando chave. **Não alertar, não cobrar e não propor ações sobre eles até o Ricardo dizer que estamos liberados.** `gabi-brain-notas.timer` está desligado (religar: `sudo systemctl enable --now gabi-brain-notas.timer`).

## Aberto
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| AT1 | Marcar agenda e responder no Teams com anuência do Ricardo (ADR-024) | R | 🔧 mergeado (PR #2) e instalado em 22/10, migração 0076 aplicada, `envios.escrita` desligado; faltam os passos do dono no runbook `#envios` | passos do dono feitos e um envio real conferido |
| A2 | Uma semana de aceite: conferir telas Agenda, Prioridades e "Na lixeira" contra o app do Google | R | 🔧 | semana sem erro anotada |
| A7 | Nibo: renovar `NIBO_TOKEN` (401 desde 16/10) | R | ⏸ on hold (chave da Nibo) | `systemctl start gabi-brain-notas` sem erro |
| C3 | Conferir `NIBO_TOKEN` e as rotas `/partners`, `/customers`, `/categories` com dado real | R+C | ⏸ on hold (chave da Nibo) | G8 fechado |
| HE1 | Hermes Onda 1 (ADR-028): instalar pelo runbook `#hermes-onda1` (`sudo ~/instalar-brain.sh`, backup `config.yaml.bak-antes-onda1`, acrescentar `familia_registrar_pessoa` e `familia_registrar_pet`, SOUL, restart do `hermes-gateway`, `/new` nos dois canais); depois o assistente aplica o que o Ricardo ditou ao Hermes em 24/10 (lido do `state.db`: irmãos, mãe, pai falecido, sobrinhos, ex-esposas, companheira, filhas, dona do apto da Gigi e Cookie) com `quem='ricardo (ditado ao Hermes em 24/10, via Claude)'`, mostra a lista ao Ricardo e confere com `familia_listar` e `auditar_promessas` | R+C | ✅ instalado 25/10; ditado aplicado (12 pessoas + Cookie), auditar_promessas 0 casos; falta `/new` e o Ricardo conferir a lista | ditado de 24/10 no brain e conferido pelo Ricardo, 0 casos novos em `auditar_promessas` |
| HE2 | Hermes Onda 2 (ADR-028): instalar pelo runbook `#hermes-onda2` (`sudo ~/instalar-brain.sh`, escopo `contatos` no token, backup `config.yaml.bak-antes-onda2`, include com 39 ferramentas, SOUL, restart do `hermes-gateway`, `/new` nos dois canais) | R | ⏳ instalada 26/10; falta `/new` nos dois canais | Hermes responde contatos, a receber e corpo de e-mail com dado do brain |
| HE3 | Hermes Onda 3 (ADR-028): instalar pelo runbook `#hermes-onda3` (backup `gabi.db.antes-onda3-<data>`, `sudo ~/instalar-brain.sh` com a migração 0082, backup `config.yaml.bak-antes-onda3`, include com 44 ferramentas, SOUL, restart do `hermes-gateway`, `/new` nos dois canais) | R | 🔧 instalada 26/10; passo 8 conferido pelo Claude via `hermes -z` em 26/10 (a receber id 1 lançado e cancelado; regra "sempre lixo" criada e removida); falta `/new` nos dois canais e o teste da lixeira com e-mail real | Hermes registra um a receber, move e-mail para a lixeira e cria regra "sempre lixo", e o Ricardo desfaz cada um |
| GO1 | Ligar o Google (contatos, agenda, e-mail) em resper@gmail.com, resper@bekaa.eu, backoffice@bekaa.eu e a conta do esper.ws: app OAuth "Em produção", `tools.obter_token_google <conta> --gravar` (4×), restart `gabi-brain-fontes`; o assistente libera as fontes (lixeira desligada) e confere a 1ª rodada | R+C | 🔧 liberado 26/10 | as 4 contas sincronizam contatos, agenda e e-mail |
| G13 | Tailscale da família: definir quem entra e para ver o quê (hoje toda rota é só do boss) antes de convidar | R | ❓ | decisão de quem e o quê |
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
