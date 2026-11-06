# Hermes enxuto: política brain × Hermes, limpeza de skills e plugins (spec)

Data: 06/11/2026 · Dono: Ricardo · Caminho: arquitetural (política + configuração de um sistema que outros fluxos usam) · Abordagem escolhida: **A, desligar por configuração**.

## 1. Objetivo
O Hermes veio com muitas skills e plugins. O brain continua sendo a **fonte única de verdade** dos dados do Ricardo e da família, e nada que o Hermes já faz bem deve ser reinventado no brain. Sucesso =
1. Uma regra escrita, curta, que decide o que é do brain e o que é do Hermes.
2. O Hermes só com o que serve à Gabi: nada que dispute com o brain os dados do Ricardo, nada que envie para fora sozinho.
3. As sobreposições conhecidas resolvidas ou registradas como decisão.

Fora do escopo: mudar código do brain; instalar plugin ou skill da comunidade; mexer em segredos; mexer na conta ou no canal do WhatsApp.

## 2. Estado atual (levantado em 06/11, só leitura)
- MCP: só `gabi_brain` (71 ferramentas pelo `include`).
- Plugins: 59 embutidos, nenhum do Ricardo; ~40 ligados. `a2a-platform` está ligado, mas o toolset `a2a` está desligado e não consta nas listas do Telegram e do WhatsApp.
- Skills: 59 (só `gabi-brain` é nossa).
- Toolsets no Telegram e no WhatsApp: `clarify`, `connections`, `cronjob`, `image_gen`, `memory`, `session_search`, `skills`, `todo`, `tts`, `vision`, `web`. Sem `terminal`, `file`, `browser`, `code_execution`, `kanban`.
- O `stt` do Hermes está ligado (português). O brain também transcreve áudio de projeto com `faster-whisper` (ADR-034).
- Duas rotinas (`cronjob`) foram criadas em 06/11 às 04:28 e não sabemos a origem.

## 3. Política (permanente)
**Regra:** dado do Ricardo ou da família é lido e gravado só pelo brain. Capacidade genérica (web, imagem, voz, mapas, pesquisa, agendar rotina) é do Hermes e o brain nunca a reimplementa.

**Critério para qualquer skill ou plugin novo** (as quatro respostas precisam ser "não" para entrar):
1. Lê ou grava dado do Ricardo ou da família fora do brain?
2. Faz o que uma ferramenta do brain já faz?
3. Pode enviar algo para fora (e-mail, mensagem, convite, pagamento) sem o clique do Ricardo no painel?
4. É da comunidade ou de origem não vetada?

A política entra como uma seção curta no `docs/PLANO-DEFINITIVO.md` e como uma linha no SOUL (o Hermes deve recusar gravar fato de pessoa em memória própria; isso já consta nas regras de gravação do SOUL).

## 4. Limpeza (abordagem A)
Tudo por configuração, reversível, sem apagar arquivo.

**4.1 Skills a desligar (47 de 59)**
- Concorrem com o brain (grupo 1, 14): `google-workspace`, `himalaya`, `email-inbox-triage`, `notion`, `box`, `airtable`, `obsidian`, `llm-wiki`, `pdf`, `meeting-action-items`, `document-to-action-items`, `weekly-review-planning`, `teams-meeting-pipeline`, `sdlc-review`.
- Não servem à Gabi (grupo 2, 33): as 4 da Apple (`apple-notes`, `apple-reminders`, `findmy`, `imessage`); as 12 de `software-development`; as 9 de `creative` (todas menos `humanizer`); as 5 de `autonomous-ai-agents`; `xurl`, `songsee`, `gif-search`.

**4.2 Skills que ficam (12):** `gabi-brain`, `humanizer`, `maps`, `youtube-content`, `grounded-citations`, `blocked-page-recovery`, `arxiv`, `product-price-monitor`, `competitor-news-monitor`, `docx`, `xlsx`, `powerpoint`.

**4.3 Plugins a desligar:** gateways de plataformas não usadas (`buzz`, `dingtalk`, `discord`, `feishu`, `google_chat`, `irc`, `line`, `matrix`, `mattermost`, `ntfy`, `photon`, `raft`, `simplex`, `slack`, `sms`, `teams`, `wecom`) e `a2a-platform`. Ficam `telegram-platform`, `whatsapp-platform` e os de autenticação do painel. `email-platform`: desligar só se for confirmado que o Hermes não usa e-mail como canal. Provedores de web, imagem e vídeo: manter um de cada em uso e desligar os outros só depois de identificar qual está em uso e testar; se não for possível identificar, deixar como está.

**4.4 Toolset `todo`:** desligar no Telegram e no WhatsApp (atividades são do brain, ADR-033). `memory`, `cronjob`, `web`, `vision`, `image_gen`, `tts`, `clarify`, `session_search`, `skills` e `connections` ficam.

**4.5 Segurança da operação**
- Backup antes: `config.yaml` e qualquer arquivo de estado que `hermes plugins` ou `hermes skills` alterem (conferido por comparação antes e depois).
- Aplicar em lotes pequenos, na ordem: toolset `todo`, plugins de gateway, skills do grupo 2, skills do grupo 1. Depois de cada lote, `hermes plugins list` e `hermes skills list` e uma conversa de teste.
- Desfazer: restaurar o backup do `config.yaml` e `hermes plugins enable` ou religar a skill; reiniciar o gateway; `/new`.
- Reiniciar o `hermes-gateway` e mandar `/new` nos dois canais é passo do Ricardo.
- Se o desligamento de uma skill só puder ser feito por `hermes skills config` (interativo), é o Ricardo quem roda, com a lista fechada nesta spec.

## 5. Sobreposições a resolver
| # | Tema | Decisão |
|---|---|---|
| S1 | Memória do Hermes (`~/.hermes/memories`) | Revisar o conteúdo. Fato de pessoa ou dinheiro que devia estar no brain: propor a migração, que só acontece com o "sim" do Ricardo. O Hermes não grava fato de pessoa na própria memória. |
| S2 | Transcrição duplicada (Hermes `stt` × brain `faster-whisper`) | Medir primeiro: mandar um áudio de teste e ver qual texto chega ao Hermes. Se o texto do Hermes basta, o fato do projeto usa essa transcrição e o brain deixa de transcrever (mudança em outra spec, ADR-034). Se não, fica como está. Nenhuma mudança nesta spec. |
| S3 | `a2a` | Confirmar que não há porta nem rota expostas; desligar o plugin (4.3). |
| S4 | Rotinas de 06/11 às 04:28 | Listar pelo comando de cron do Hermes e mostrar ao Ricardo; mantê-las ou removê-las só por decisão dele. |
| S5 | `todo` × atividades | Resolvido em 4.4. |

## 6. Atualizações de documentação
- Guia do Hermes (`~/COMO-USAR-HERMES.md` e o resumo de uma tela): incluir o que o Hermes faz por conta própria (web, imagem, voz, mapas, rotinas, pesquisa).
- `deploy/hermes/SOUL.md`: manter o resumo de uma tela em sincronia com o guia curto.
- `docs/BACKLOG.md`: item novo "Hermes enxuto" até a conclusão.

## 7. Verificação
- `hermes plugins list` e `hermes skills list` batem com as seções 4.1 a 4.3.
- `hermes tools list` não mostra `todo` para Telegram e WhatsApp.
- Conversa de teste depois do `/new`: "o que você pode fazer?" (macro), uma pergunta com web, e um pedido do brain ("saldo?"), que continua funcionando.
- Suíte de testes do brain passa (a spec não toca código do brain, então serve só para provar que nada mudou).

## 8. Riscos
- Desligar um plugin de que o Hermes depende (provedor de web ou imagem) → lotes pequenos e teste depois de cada um.
- `hermes update` pode religar o que é embutido → conferir a lista depois de cada update; `opt-out` das skills embutidas fica como etapa futura, decidida depois de um mês de uso.
- O desktop e o CLI têm toolsets próprios, mais amplos que Telegram e WhatsApp; esta spec não os restringe.
