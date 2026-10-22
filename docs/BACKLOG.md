# gabi.brain · BACKLOG (fonte única do que falta)
**Este arquivo manda sobre o que falta.** `STATUS.md` é a retomada rápida; `PLANO-DEFINITIVO.md` guarda as decisões; `/home/ricardo/PENDENCIAS-RICARDO.md` aponta para cá.
Reescrito em 22/10/2026 depois da simplificação (ADR-023): só o que segue aberto. O backlog anterior, com o histórico de cada item fechado, está em `docs/historico/BACKLOG-ate-2026-10-21.md`.

Legenda: dono **R** = Ricardo · **C** = Claude · **R+C** = juntos. Status: 🔧 em curso · ⛔ bloqueado · ⏸ em espera · ❓ a verificar.
Regras que valem em tudo: R1 a Gabi sugere, o Ricardo decide (exceção: "para quem" certeiro, ADR-023) · R2 nenhum envio externo automático · segredos só o Ricardo coloca · dados nunca chumbados · nada no claude.ai · esquema novo = migração 0076+.
**Regra para o que vier (ADR-023):** pergunta vai para o Hermes (MCP); o painel só ganha tela quando há decisão ou lista para revisar; nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual que mostre a necessidade.

## Em espera por chave de terceiros (ordem do dono, 21/10)
Google (contatos G12), Graph da ionic e Nibo (A7/C3) aguardam chave ou consentimento. **Não alertar, não cobrar e não propor ações sobre eles até o Ricardo dizer que estamos liberados.** `gabi-brain-notas.timer` está desligado (religar: `sudo systemctl enable --now gabi-brain-notas.timer`).

## Aberto
| # | Item | Dono | Status | Pronto quando |
|---|---|---|---|---|
| SP1 | **Instalar a simplificação (ADR-023)** na VPS: confirmar tabelas vazias, parar e remover as units cortadas, `sudo ~/instalar-brain.sh`, alinhar o `tools.include` do Hermes com `docs/fontes/hermes.md` (18 ferramentas) e conferir (spec "Produção") | R+C | ⏸ aguarda autorização | API, MCP e painel no ar; rodada de extratos `conferida=1`; nenhuma unit em `failed` |
| SP2 | Decidir o que fazer com o que a simplificação deixou parado: pareamento do WhatsApp e pastas do ouvinte, cofre `saude.enc` e chave, `~/saude.key.COPIE-E-APAGUE` | R | ⏸ | decidido (apagar ou guardar) |
| A2 | Uma semana de aceite: conferir telas Agenda, Prioridades e "Na lixeira" contra o app do Google | R | 🔧 | semana sem erro anotada |
| A6 | Teto de custo do modelo: com a escuta fora, o teto global agora é só do correio. Conferir se `email_sem_modelo` voltou (não aparece desde 19/10) e se o modelo de reserva (`email-falha`, US$ 6,18 em 11 dias contra US$ 0,12 do normal) precisa de ajuste | R+C | ❓ | aviso some e custo de reserva explicado |
| A7 | Nibo: renovar `NIBO_TOKEN` (401 desde 16/10) | R | ⏸ on hold (chave da Nibo) | `systemctl start gabi-brain-notas` sem erro |
| C3 | Conferir `NIBO_TOKEN` e as rotas `/partners`, `/customers`, `/categories` com dado real | R+C | ⏸ on hold (chave da Nibo) | G8 fechado |
| H7 | 7 dias de Hermes estável + backup exportado | R+C | ⛔ depende de H5 (número dedicado, lista do Ricardo) | sem queda em 7 dias |
| F2 | Encerramento e memória (Task 16 do fechamento): atualizar a memória do Claude com o estado pós-simplificação | C | 🔧 | memória coerente com ADR-023 |

## Decisões do Ricardo sem resposta
- **Extratos 4x por dia** (em vez de 06h e 14h): muda custo de chamadas ao mcp.ai.
- **Marcação de agenda e resposta no Teams com anuência:** é envio externo; só com ADR de exceção à R2.
- **Tailscale da família (G13):** ação no admin do Tailscale, fora do código.

## Depois (sugeridos na revisão de 21/10, não escolhidos ainda)
- Achatar compromissos e conciliação (lógica do gabi-fin portada em float, 4 estados, para ~27 linhas por mês).
- Enxugar a lixeira do e-mail (8 condições, conferência ao vivo, 8 tentativas) para regras de remetente.
- Congelar a rodada diária de propostas de contatos (ADR-022 gera 0 propostas até o G12).
- Tirar do alerta "emergencial" os e-mails do próprio sistema (falhas do ness.brain, Google Cloud).
- Reduzir a frequência dos timers de Teams (5 min) e agenda (15 min).
- Microsoft Graph da ionic (G11): parado pelo administrador do tenant (`docs/fontes/graph-ionic-passo-a-passo.md`).
- Agenda financeira diária sem LLM (cron `no_agent` do Hermes, como a semanal).

## Cortado em 22/10 (ADR-023)
Escuta do WhatsApp (E1–E4), saúde (S1–S3, D8), módulo Trabalho (Frentes, Tarefas, Entregas/Linear, contatos em aberto), cobrança e reembolso PJ (C1, C2, AR2, comprovantes, pedidos), Obsidian por pessoa, perfil de normalidade (PF1), tela Configuração, 7 abas vazias do menu Gabi, ferramentas MCP sem uso (o Hermes fica com 18), índice FTS da memória. D2 (conferência travando o `dados_ate`) resolvido: a conferência só informa.

## Obsoleto (não fazer)
- **G16** reconectar XP Investimentos: a conexão saiu do mcp.ai em 11/10.
- Qualquer "plano B" no OpenClaw; trabalho novo no `gabi-fin`, `gabi-app`, `gabi-fluxos-*`, `gabi-contas-cartoes`, `gabi-guarda-sessoes`.
- Juntar correio, agenda e Teams num timer só (acopla falhas e quebra o aviso `servico_falhou`).

## Como manter
Ao fechar um item, tire-o daqui e registre a evidência (comando, número, commit) no commit ou em `STATUS.md`. Item novo entra em "Aberto" com dono, ou em "Depois" se não tem pressa.
