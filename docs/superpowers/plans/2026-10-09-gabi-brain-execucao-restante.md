# gabi.brain — Plano de execução do que falta (Fase 1 final → Fase 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (nesta sessão, inline) ou superpowers:subagent-driven-development. Steps usam checkbox (`- [ ]`). **Este plano NÃO substitui o plano mestre**: o detalhe de cada tarefa T2.x/TC.x/T3.x/T4.x (interfaces, tabelas, testes por nome) está em `/home/ricardo/handoff/docs/superpowers/plans/2026-10-08-gabi-brain-plano-mestre.md`; aqui ficam o estado real, a ordem, os gates, as entregas por fase e as tarefas novas que o mestre não tinha.

**Goal:** Entregar o gabi.brain completo (dinheiro, cobrar, trabalho, canal e depois), fase por fase, cada uma com testes, entrega instalada na VPS e aceite com dado real.

**Architecture:** Inalterada (plano mestre §3): pacote `gabi` (FastAPI + SQLite) em `/opt/gabi-brain`, API só por socket Unix atrás de `tailscale serve`, MCP em `127.0.0.1:8081`, painel React estático, rodadas por timers systemd (extratos **06h e 14h BRT**, saldos de hora em hora).

**Tech Stack:** Python 3.12, FastAPI, SQLite WAL+FTS5, SDK MCP, React/Vite, pytest, vitest, systemd, Tailscale.

**Spec:** `/home/ricardo/handoff/docs/superpowers/specs/2026-10-08-gabi-brain-migracao-design.md`

## Global Constraints
- Restrições R1–R17 do plano mestre §2 valem para tudo (sugere/decide, sem efeito externo automático, só Tailscale, tudo registrado, **nenhum segredo passa por mim**, nada de dado fixo no código, dinheiro em centavos, fidelidade ao protótipo).
- Ciclo de toda tarefa: teste vermelho pelo motivo certo → mínimo para passar → `pytest -q` e `npm test` verdes → doc → commit. Instalar com `sudo bash deploy/instalar.sh --confirmo-backup-exportado`; conferir `systemctl show gabi-brain-api -p ActiveEnterTimestamp`.
- Painel: regenerar `python -m tools.gerar_amostras`, `python -m tools.gerar_docs_api` e `python -m tools.capturas` quando a API/telas mudarem (há testes de frescor).
- Regra do projeto: **só se avança de fase com dado real validado.** Código de fase seguinte pode ser escrito contra servidor falso enquanto o aceite roda (decisão D2), mas a fase só é *aceita* com dado real.
- `dados_ate` = última rodada **conferida**; nada de "ok" que não conferiu.

## Estado real (09/10/2026)
| Bloco | Estado |
|---|---|
| Fase −1, Fase 0 (T0.1–T0.9) | feitas e instaladas |
| Fase 1 T1.0–T1.13 | feitas e instaladas; 643 testes pytest + 25 vitest verdes |
| Fase 1 pendências | conferência a calibrar (F1.A), minors do painel (F1.B–F1.G), G14, aceite T1.14 |
| Fase 2, Canal, Fase 3, Fase 4 | não iniciadas |
| Gates | G1–G4 feitos; **G5 feito 09/10 (15 contas `sim`)**; G6–G13 abertos; **G14 aberto** |
| Fontes com problema | C6 Bank Empresas e XP Investimentos sem atualizar (issue 0001; é seed, não dev) |

## Decisões abertas (do Ricardo)
- **D1 — o que é "buraco" na conferência** (F1.A). Padrão proposto: conta corrente só reprova por buraco com ≥ 2 dias úteis seguidos sem movimento **e** último sync ok > 24 h; cartão nunca; débito de fatura ainda não publicado explica a diferença do `saldo_final`.
- **D2 — paralelismo.** Padrão proposto: escrever Fase 2 (e depois Fase 3) contra servidores falsos enquanto o relógio do T1.14 (7 e 14 dias) corre; aceite de cada fase só com dado real e gates cumpridos.
- **D3 — ordem do Canal.** Mantida a decisão de 08/10: TC.* e desligar o OpenClaw **só depois** das Fases 0–4 aceitas (Hermes+OpenRouter só ao fim).

## Review Focus (o que os testes de tarefa não cobririam sozinhos)
1. Rodada que termina `ok` mas nunca fica `conferida` (faixa amarela para sempre): F1.A fixa com casos reais da rodada 18 (cartão, conta sem movimento, fatura pendente).
2. Contador do sino/menu divergente da tela (diz 3, a tela mostra 2): F1.B compara a contagem com a lista.
3. Sugestão editada que vira regra ativa sem aprovação: F1.D (R1).
4. Fase 2 gravar no Nibo duas vezes ou sem a confirmação textual: T2.4 (plano mestre).
5. Fonte parada passando por ok depois que novas fontes entram (Paperless, Nibo, Graph, Google): cada cliente novo entra no `envelope` com teste.

---

## FASE 1 — fechamento

### Task F1.A: Calibrar a conferência com dado real (decisão D1)
**Files:** Modify `gabi/dinheiro/conferencia.py`; Test `tests/dinheiro/test_conferencia.py`
**Interfaces:**
- Consumes: `conferir(con, rodada_id, conta_id, hoje) -> list[Conferencia]`, `marcar_conferida(con, rodada_id) -> bool`, `conta_estado.ult_sync_ok`, `faturas` abertas (`contas_pagar.faturas_abertas`).
- Produces: mesmas assinaturas; `_dias_sem_buraco(con, conta_id, hoje, tipo)` passa a receber o `ult_sync_ok` da conta; `_saldo_final` aceita diferença igual a débito de fatura ainda não publicado, com `detalhe` dizendo qual.
- [ ] **Step 1: Ler a evidência.** `select cf.conta_id, cf.tipo, cf.detalhe from conferencia cf where rodada_id=<última> and ok=0` (rodada 18 de 09/10: contas 5–9, 12) e guardar como casos em `tests/golden/conferencia_real_2026-10-09.json` (valores, sem nomes).
- [ ] **Step 2: Testes vermelhos** — `test_cartao_nunca_reprova_por_buraco`, `test_conta_corrente_com_1_dia_util_sem_movimento_e_sync_recente_passa`, `test_conta_corrente_2_dias_uteis_seguidos_sem_movimento_e_sync_antigo_reprova`, `test_saldo_final_explicado_por_fatura_pendente_passa_com_detalhe`, `test_saldo_final_sem_explicacao_continua_reprovando`, `test_rodada_com_contas_sim_todas_ok_fica_conferida`.
- [ ] **Step 3: Implementar** conforme D1; regra e limites em constantes nomeadas no topo do módulo (valores só mudam por ADR `docs/adr/009-regra-de-buraco.md`).
- [ ] **Step 4: Verificar** `pytest -q tests/dinheiro` verde; reinstalar; `sudo systemctl start gabi-brain-extratos` e conferir `rodada.conferida=1` e a faixa do painel sem "desatualizado".
- [ ] **Step 5: Commit** (`fix(conferencia): calibra buraco e saldo_final com dado real`).
**Entrega:** faixa verde com `dados_ate` real. **Bloqueio:** D1.

### Task F1.B: Contadores do sino e do menu
**Files:** Create `gabi/rotas/contagens.py`; Modify `gabi/rotas/__init__.py`, `painel/src/componentes/Shell.tsx`, `painel/src/lib/api.ts`; Test `tests/rotas/test_contagens.py`, `painel/tests/telas.test.tsx`
**Interfaces:** Produces `GET /api/v1/contagens` → envelope com `dados = {"sino": int, "menu": {"regras": int, "cartoes": int, "pagar": int, "assinaturas": int}}` (cada número = itens que exigem decisão: sugestões pendentes, faturas/cartões a conferir, compromissos atrasados, assinaturas com alerta). `useContagens(): {sino: number, menu: Record<string, number>}`.
- [ ] **Step 1: Testes** — `test_contagem_sugestoes_igual_a_lista` (n da contagem == `len(GET /sugestoes?estado=pendente)`), `test_contagem_so_boss`, `test_contagem_zero_nao_mostra_selo` (vitest), `test_sino_soma_os_selos`.
- [ ] **Step 2: Implementar** a rota reutilizando as consultas das rotas existentes (sem SQL duplicado) e o selo no `Shell`.
- [ ] **Step 3: Regenerar** amostras, docs da API, capturas; `pytest -q` e `npm test`; commit.
**Entrega:** sino e menu com contador.

### Task F1.D: Editar o destino da sugestão de regra
**Files:** Modify `gabi/rotas/dinheiro.py`, `gabi/dinheiro/regras.py`, `painel/src/telas/Regras.tsx`; Test `tests/dinheiro/test_regras.py`
**Interfaces:** `PATCH /api/v1/sugestoes/{id}` body `{"categoria_id"?: int, "para_quem_id"?: int}` → 200 com a sugestão atualizada; `regras.editar_sugestao(con, id: int, *, categoria_id: int | None, para_quem_id: int | None, por: str) -> Sugestao`.
- [ ] **Step 1: Testes** — `test_editar_sugestao_nao_ativa_a_regra`, `test_aprovar_apos_editar_cria_regra_com_o_destino_editado`, `test_editar_sugestao_ja_aprovada_da_409`, `test_editar_registra_decisao` (R4).
- [ ] **Step 2: Implementar**, **Step 3: Verificar e commit.**

### Task F1.E: Filtro "só assinatura" em Cartões
**Files:** Modify `painel/src/telas/Gastos/Cartoes.tsx`; Test `painel/tests/telas.test.tsx`
- [ ] Teste `Cartoes_filtro_so_assinatura_esconde_o_resto` (lista com 3 tipos → só os de assinatura) → implementar o chip conforme o protótipo (R17) → commit.

### Task F1.F: Custo da Gabi em reais
**Files:** Modify `gabi/rotas/gastos.py` (custo), `painel/src/componentes/CustoGabi.tsx`; Test `tests/rotas/test_gastos.py`
**Interfaces:** `GET /api/v1/gastos/custo` ganha `cambio_brl: string | null` lido de `parametro` (chave `cambio_usd_brl`, editável em Cadastros; **nunca fixo no código**, R6).
- [ ] Testes `test_custo_sem_cambio_mostra_so_usd`, `test_custo_com_cambio_calcula_brl_em_centavos`; painel mostra "R$" quando há câmbio. Commit.

### Task F1.G: Resumo das rodadas em "A pagar"
**Files:** Modify `painel/src/telas/Caixa/APagar.tsx`; usa `GET /api/v1/rodadas` (já existe)
- [ ] Testes `APagar_mostra_ultimas_rodadas_com_estado_e_conferida`, `APagar_rodada_nao_conferida_mostra_motivo`; implementar bloco "Rodadas" (06h/14h) com estado, lidos, conferida; commit.

### Task F1.H: Gate G14 — aprovação tela a tela (Ricardo)
- [ ] `python -m tools.capturas` regenera `docs/design/*-{prototipo,app}-*.png`; **PARAR** e pedir ao Ricardo a aprovação de cada tela (as capturas em `docs/design/`); registrar aprovações e correções; desvio só por ADR assinado (R17).

### Task F1.I: Aceite da Fase 1 (T1.14)
- [ ] Rodando ≥ 7 dias seguidos com `conferida=1` nas rodadas 06h/14h; ≥ 90 % classificado sem intervenção após 14 dias; telas e MCP verificados; `docs/aceite-fase-1.md` com evidência e data; mostrar ao Ricardo o que está no ar e o que ficou pendente. **Libera a aceitação (não o código) da Fase 2.**

**Entrega da Fase 1:** painel completo da Fase 1 instalado, sem pendência, com `docs/aceite-fase-1.md`.

---

## FASE 2 — Cobrar (T2.1–T2.10 do plano mestre)
Ordem: **T2.1** Paperless (G7) → **T2.2** vínculos → **T2.3** Nibo leitura (G8) → **T2.5** reembolsos → **T2.4** lote Nibo (única gravação externa) → **T2.6** cobrança (só rascunho, ADR-006) → **T2.7** pedidos → **T2.8** MCP propostas → **T2.9** telas → **T2.10** aceite.
- Cada cliente (Paperless, Nibo) nasce com servidor falso e testes do mestre (`test_cliente_nao_expoe_metodo_de_exclusao`, `test_nenhuma_rota_de_exclusao_no_codigo`, `test_executar_duas_vezes_nao_duplica`).
- Cada fonte nova entra em `envelope.IGNORADAS`/fontes e em `docs/fontes/<fonte>.md`.
- **Entrega:** ≥ 80 % de comprovantes casados; lote Nibo roda 2× sem duplicar em conta real com confirmação do Ricardo; pedido real do canal aparece em Pedidos; `docs/historico/aceite-fase-2.md`. **Gates:** G7, G8, G14 (T2.9).

## FASE 3 — Trabalho (T3.1–T3.7)
Ordem: **T3.1** Graph (G11) e **T3.2** Google (G12) em paralelo → **T3.3** e-mail/agenda/tarefas → **T3.4** frentes → **T3.5** Hoje → **T3.6** telas → **T3.7** aceite.
- Testes-chave: `test_deduplica_por_message_id_entre_google_e_graph`, `test_expurgo_sem_regra_ligada_nao_apaga_nada`, `test_hoje_carrega_em_menos_de_1s_com_dados_reais`, `test_criar_rascunho_nao_chama_send`.
- **Entrega:** 7 caixas com itens e sem `message_id` duplicado; Hoje < 1 s no celular; `docs/aceite-fase-3.md`. **Gates:** G11, G12, G14.

## FASE 4 — Depois (só por pedido do Ricardo)
T4.1 saúde cifrada → T4.2 exames/Família → T4.3 Rumo e Linear → T4.4 acesso da família (G13) → T4.5 assistente de configuração → T4.6 Obsidian. Cada item abre com um mini-spec aprovado antes de código.

## CANAL (TC.1–TC.6) — por último (D3)
Só com Fases 0–4 aceitas: instalar Hermes+OpenRouter (G9), MCP, resumo da manhã, identidade por remetente (spike → ADR-007), WhatsApp (G10), **desligar o OpenClaw** (backup exportado, 7 dias de Hermes estável, `--dry-run` antes).

## Auto-revisão
- **Cobertura:** Fase 1 final (F1.A–I), Fases 2–4 e Canal apontadas ao mestre, com ordem, gates, testes-chave e entrega por fase.
- **Consistência:** assinaturas novas (`/contagens`, `PATCH /sugestoes/{id}`, `cambio_brl`) usadas só nas tasks que as criam; amostras/docs regenerados em cada uma.
- **Proporção:** o detalhe de T2–T4 fica no mestre de propósito; este arquivo só decide o que o mestre não sabia.
