# gabi.brain · BACKLOG (fonte única do que falta)
**Este arquivo manda sobre o que falta.** `STATUS.md` é a retomada rápida; `PLANO-DEFINITIVO.md` guarda as decisões; `/home/ricardo/PENDENCIAS-RICARDO.md` aponta para cá.
Reescrito em 22/10/2026 depois da simplificação (ADR-023): só o que segue aberto. O backlog anterior, com o histórico de cada item fechado, está em `docs/historico/BACKLOG-ate-2026-10-21.md`.

Legenda: dono **R** = Ricardo · **C** = Claude · **R+C** = juntos. Status: 🔧 em curso · ⛔ bloqueado · ⏸ em espera · ❓ a verificar.
Regras que valem em tudo: R1 a Gabi sugere, o Ricardo decide (exceção: "para quem" certeiro, ADR-023) · R2 nenhum envio externo automático · segredos só o Ricardo coloca · dados nunca chumbados · nada no claude.ai · esquema novo = migração 0076+.
**Regra para o que vier (ADR-023):** pergunta vai para o Hermes (MCP); o painel só ganha tela quando há decisão ou lista para revisar; nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual que mostre a necessidade.

## Em espera por chave de terceiros (ordem do dono, 21/10)
**26/10: Google (G12, 4 contas) e Tailscale da família (G13) liberados pelo Ricardo** (itens GO1 e G13 em "Aberto"). Graph da ionic e Nibo (A7/C3) seguem aguardando chave. **27/10: Tailscale da família (G13) desligado de novo** ("serão incluídos oportunamente"); volta quando o Ricardo disser quem entra. **Não alertar, não cobrar e não propor ações sobre eles até o Ricardo dizer que estamos liberados.** `gabi-brain-notas.timer` está desligado (religar: `sudo systemctl enable --now gabi-brain-notas.timer`).

## Aberto
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| AT1 | Marcar agenda e responder no Teams com anuência do Ricardo (ADR-024) | R+C | 🔧 27/10: `envios.escrita` LIGADO, contas de agenda gmail/ness/bekaa, `painel.url`; token do Hermes já tinha `envios`; gmail já pode criar evento. Agenda da ness ok (Calendars.ReadWrite); "cliente público" ligado pelo Ricardo em 27/10. Login do Teams feito em 27/10 (`GRAPH_NESS_TEAMS_REFRESH` gravado, `gabi-brain-fontes` reiniciado). Faltam: o token da resper@bekaa.eu com `calendar.events` e o teste (Hermes propõe, você clica Enviar em Envios) | um evento e uma mensagem no Teams enviados pelo painel e conferidos |
| A2 | Uma semana de aceite: conferir telas Agenda, Prioridades e "Na lixeira" contra o app do Google | R | 🔧 | semana sem erro anotada |
| A7 | Nibo: renovar `NIBO_TOKEN` (401 desde 16/10) | R | ⏸ on hold (chave da Nibo) | `systemctl start gabi-brain-notas` sem erro |
| C3 | Conferir `NIBO_TOKEN` e as rotas `/partners`, `/customers`, `/categories` com dado real | R+C | ⏸ on hold (chave da Nibo) | G8 fechado |
| HE3 | Hermes Onda 3 (ADR-028): instalar pelo runbook `#hermes-onda3` (backup `gabi.db.antes-onda3-<data>`, `sudo ~/instalar-brain.sh` com a migração 0082, backup `config.yaml.bak-antes-onda3`, include com 44 ferramentas, SOUL, restart do `hermes-gateway`, `/new` nos dois canais) | R | 🔧 instalada 26/10; passo 8 conferido pelo Claude via `hermes -z` em 26/10 (a receber id 1 lançado e cancelado; regra "sempre lixo" criada e removida); `/new` feito 26/10; falta o teste da lixeira com e-mail real | Hermes registra um a receber, move e-mail para a lixeira e cria regra "sempre lixo", e o Ricardo desfaz cada um |
| GO1 | Google nas contas pessoais/Bekaa | R+C | ✅ 27/10: e-mail das 4 contas lendo (lixeira desligada no gmail e esper.ws); contatos do gmail na leitura (People API ativada; "Outros contatos" fora, decisão do Ricardo); agenda do gmail e esper.ws desligada por escolha dele | — |
| DS1 | Despesas (ADR-032, item 3 de 26/10): criar, mudar, dispensar, encerrar e excluir pelo painel e pelo Hermes; instalar pelo runbook `#despesas` (backup `gabi.db.antes-despesas-<data>`, `sudo ~/instalar-brain.sh` com a migração 0085, backup `config.yaml.bak-antes-despesas`, include com 55 ferramentas, SOUL, restart do `hermes-gateway`, `/new` nos dois canais) | R | 🔧 mergeada (`454609c`) e instalada 27/10 (migração 0085); falta o teste (Sabrina encerrada no painel; Hermes cria, dispensa um mês e exclui uma despesa de teste) | Sabrina encerrada pelo painel e some de A Pagar; Hermes cria, dispensa um mês e exclui uma despesa de teste depois do sim |
| AV1 | Atividades (ADR-033): recado ao Hermes vira to-do, com lista no painel e aviso no Telegram; instalar pelo runbook `#atividades` (backup `gabi.db.antes-atividades-<data>`, `sudo ~/instalar-brain.sh` com a migração 0086, escopo `atividades` no token do Hermes, backup `config.yaml.bak-antes-atividades`, include com 60 ferramentas, SOUL, restart do `hermes-gateway`, `/new` nos dois canais) | R | ✅ 27/10: instalada e aceita pelo Ricardo (`/new` feito, teste real funcionou) (migração 0086, backup `gabi.db.antes-atividades-2026-10-27`, escopo `atividades` no token 3, include com 60, SOUL, restart do `hermes-gateway` 15:2x; `atividade_listar` conferida via `hermes -z`) | Hermes cria uma atividade com hora 20 min à frente, ela aparece em Dia › Atividades e o aviso chega no Telegram; "já fiz" a tira da lista |
| PJ1 | Projetos (ADR-034): gestão de projetos de qualquer tipo conduzida pelo Hermes (ou outro agente MCP) dentro do brain: projeto, atividades com dependência, pessoas, dinheiro (orçamento e gasto), fatos e anexos (print, imagem, áudio com transcrição local); aviso de projeto parado; tela Projetos | R | 🔧 mergeada e instalada 27/10; timer `gabi-brain-anexos` ligado; faltam os passos do runbook `#projetos` e o teste real (backup `gabi.db.antes-projetos-<data>`, pasta dos anexos, escopo no token do Hermes, backup `config.yaml.bak-antes-projetos`, include com 70, SOUL, restart do `hermes-gateway`, `/new` nos dois canais, transcrição opcional) | projeto de teste criado pelo Hermes com 3 atividades, print e áudio viram fatos depois do sim, tudo visível no painel |
| CV1 | Convites de agenda recebidos (ADR-035) | R | ✅ 06/11: instalado (migração 0088, painel, include do Hermes com 71, SOUL, restart); teste real: convite "teste" avisado, Hermes propôs aceitar, clique em Enviar às 10h41 (Brasília), Outlook confirmou `accepted`. Pendente só: conferir se o conflito "(sem título)" do aviso era real | — |
| H7 | 7 dias de Hermes estável + backup exportado | R | ⏸ 06/11: Hermes estável conferido (só parou no reinício planejado de 06/11; antes disso rodou sem queda). Exportação semanal para fora da VPS **deixada para depois por decisão do Ricardo**: `gabi-brain-exportacao` é pulado desde 01/11 porque falta `/etc/gabi/backup.pub` (chave pública que ele gera; a privada fica com ele). Backup diário local ok. Não cobrar até ele liberar | `/etc/gabi/backup.pub` no lugar e uma exportação semanal concluída |

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
