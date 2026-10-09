# gabi.brain · TRILHA até o fim
Criada: 09/10/2026. Fonte de verdade da ordem; detalhe de cada tarefa em `/home/ricardo/handoff/docs/superpowers/plans/2026-10-08-gabi-brain-plano-mestre.md` e estado real em `docs/STATUS.md`.

"Terminar" = Fases 0–3 **aceitas com dado real**, Fase 4 entregue por pedido, depois Canal (Hermes) e desligar o OpenClaw. Código eu escrevo; **aceite só com dado real e gate cumprido** (regra do projeto). Por isso a trilha tem duas pistas: a minha (código, contra servidor falso) e a do Ricardo (gates e relógios).

## Pista A — o que eu faço sozinho, em ordem
| # | Entrega | Depende de | Pronto quando |
|---|---|---|---|
| A1 ✅ | **T3.3** migração 0011 (caixa_email, item_email, evento, tarefa) + e-mail/agenda/tarefas | nada | testes do mestre verdes (message_id único, só cabeçalho+trecho, relevante com motivo, expurgo sem regra não apaga, conflito só propõe) |
| A2 ✅ | **T3.4** frentes (reconhecer/confirmar/abrir, sem nome fixo) | A1 | sugestão não entra sem confirmação |
| A3 ✅ | **T3.1** cliente Graph (servidor falso; só rascunho, sem `send`) e **T3.2** cliente Google (idem; dedupe por Message-ID entre os dois) | A1 | testes do mestre; `docs/fontes/{graph,google,caixas-de-email}.md` |
| A4 ✅ | **T3.5** `hoje`, rotas de trabalho, MCP `hoje_resumo`/`frentes_*` | A1–A3 | Hoje < 1 s, só de tabelas prontas |
| A5 ✅ | **T3.6** telas Hoje, Frentes, Agenda, Mensagens, Tarefas + capturas | A4 | vitest verde, capturas lado a lado geradas p/ G14 |
| A6 | Fase 2: aba "Notas a receber" (NFS-e) e job de ingestão de comprovantes do Paperless | A6 precisa de documento real (G7); NFS-e precisa definir fonte | escrito contra fake; validado no aceite T2.10 |
| A7 | Fase 4 (T4.1–T4.6): cada item abre com mini-spec aprovado | pedido do Ricardo | só por pedido |
| A8 | **Canal TC.1–TC.6** | Fases 0–4 aceitas | por último; `--dry-run` antes de desligar o OpenClaw |

Ciclo de cada item: teste vermelho → mínimo → `pytest -q` + `npm test` → doc → commit → instalar (`sudo bash deploy/instalar.sh --confirmo-backup-exportado`) → atualizar `STATUS.md` e o ledger.

## Pista B — o que só o Ricardo destrava
| Gate | Ação | Libera |
|---|---|---|
| issue 0001 | reconectar **C6** e **XP Investimentos** no mcp.ai | `conferida=1` → aceite T1.14 |
| relógio T1.14 | 7 dias seguidos com rodada 06h/14h `conferida=1`; ≥90 % classificado em 14 dias | `docs/aceite-fase-1.md` |
| G7 | token admin do Paperless (assistente cria o usuário `gabi`) | T2.1 real, ingestão de comprovantes |
| G8 | `NIBO_TOKEN` em `/etc/gabi/brain.env` | T2.3/T2.4 real (confirmar `/partners`, `/customers`, `/categories`, `items`) |
| Cadastros | relação/e-mail das empresas, quem pode pedir, `nibo_category_id`, sócio do Nibo | T2.10 |
| G14 (Fase 2) | aprovar capturas das telas Cobrar/Pedidos | aceite T2.9 |
| G11 | app no Entra ID da IONIC (certificado) + aprovação do admin | T3.1 real |
| G12 | projeto Google Cloud: OAuth (ness, Gmail) + conta de serviço (bekaa.eu, esper.ws) | T3.2 real |
| G14 (Fase 3) | aprovar capturas das telas de Trabalho | aceite T3.6 |
| G13 | Tailscale comporta a família | T4.4 |
| G9/G10 | Hermes + bot BotFather; número de WhatsApp dedicado | Canal |

## Marcos de aceite (ordem)
1. **Fase 1** — T1.14: ≥ 7 dias conferidos (estimativa: depende de reconectar C6/XP; relógio começa na 1ª rodada `conferida=1`).
2. **Fase 2** — T2.10: ≥ 80 % de comprovantes casados; lote Nibo 2× sem duplicar; pedido real do canal em Pedidos.
3. **Fase 3** — T3.7: 7 caixas com itens, zero `message_id` duplicado, Hoje < 1 s no celular.
4. **Fase 4** — por pedido.
5. **Canal** — Hermes estável 7 dias, só então desligar o OpenClaw.

## Regras que valem em toda a trilha
Não mexer em segredos (Ricardo coloca). Nada no claude.ai. Dados nunca chumbados. Esquema novo = migração **0011+** (0009 e 0010 congeladas). Nenhum envio externo automático (R2). Custo da Gabi em US$.

## Andamento
- 09/10 noite: A1–A5 feitas (código, testes, painel). Falta de A5: capturas p/ G14 e faixa "Reconectar" (dependem de G11/G12). Próximo da pista A: job de rodada do Trabalho (precisa de credencial real para validar) e A6.
- 09/10 noite: Ricardo aceitou todas as fases e aprovações (por decisão, sem dado real). Pista A segue: serviço `gabi-brain-fontes`, job de rodada do Trabalho, A6. Pista B técnica (tokens, reconexões) continua com o Ricardo.
