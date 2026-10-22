# gabi.brain — Plano de Finalização

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o gabi.brain: Fases 1 (Dinheiro) e 2 (Cobrar) aceitas com dado real, avisos que chegam ao Ricardo, previsão de caixa completa (entradas e saídas), virada do `gabi-financeiro` e documentação em dia. A Fase 3 segue congelada; o agente de canal (Hermes) tem plano próprio (`gabi-agent`).

**Architecture:** O gabi.brain continua um serviço único (SQLite + API + painel + MCP + timers). Cada item abaixo é um módulo pequeno sobre o que já existe: `aviso` (tabela já criada, ainda sem produtor), `nota_fiscal` (migração 0012), `previsao` (entradas), `regra`/`semear_donos` (classificação). Nada novo envia coisa para fora sem o gate do Ricardo (R2).

**Tech Stack:** Python 3.12 (stdlib + FastAPI), SQLite (WAL, FTS5), React/Vite no painel, systemd (units/timers em `deploy/`), pytest + vitest.

**Spec:** `/home/ricardo/handoff/docs/superpowers/plans/2026-10-08-gabi-brain-plano-mestre.md` (restrições R1–R17, gates G1–G14, aceites T1.14 e T2.10), `docs/historico/TRILHA.md`, `docs/STATUS.md` (estado de 09–10/10/2026) e `/home/ricardo/handoff/docs/superpowers/specs/2026-10-08-gabi-brain-migracao-design.md`.

## Estado de partida (10/10/2026, verificado)

- Fase 1: captura, conferência (rodadas 43 e 46 conferidas), caixa, classificação (categoria 4.136/4.656; "para quem" 4.511/4.656 = 96%), 53 regras, painel. Aceite T1.14 em contagem (relógio começou 09/10).
- Fase 2: cobrar/reembolsos (NESS 56 itens, IONIC 13, Bekaa 12 marcados), lote do Nibo (nunca exercitado em escrita), notas fiscais importadas (243; 193 PDF/XML), previsão de **entradas** (`gabi/cobrar/previsao.py`, rota `GET /api/v1/cobrar/previsao`, **sem tela**), pedidos (MCP pronto, sem canal).
- Fase 3: **congelada** (decisão do Ricardo, 09/10). Reabrir só com Fases 1–2 em uso diário.
- Pendências conhecidas: nenhum produtor de `aviso`; sem timer de notas; sem backup fora da VPS automático; XP Investimentos parada desde 12/08 (issue 0001); `gabi-financeiro` (OpenClaw) ainda roda em paralelo; plano mestre desatualizado.

## Global Constraints

- **R1** A Gabi sugere, o Ricardo decide. Regra, classificação e pedido só valem após aprovação dele.
- **R2** Nenhum efeito externo automático (e-mail, pagamento, exclusão). Única gravação externa: lote do Nibo, com confirmação textual. Mensagem de aviso ao próprio Ricardo exige o **gate G15** abaixo.
- **R5** Nenhuma credencial passa por mim; segredos em `/etc/gabi/*.env`, colocados por ele. Tokens só no serviço de fontes.
- **R6** Nada fixo no código: empresas, contas, pessoas, categorias, donos padrão e parâmetros vêm de tabelas/seeds editáveis.
- **R7** Dinheiro em centavos inteiros; string decimal na API; nunca `float` fora de função pura portada.
- **R9** Origem por campo: `banco|regra|gabi|voce|fonte`. `fonte` = padrão do cadastro (regra por loja vence); `voce`/`regra` nunca são sobrescritos.
- **R10** Nada de dado de fonte é apagado; cadastros têm exclusão lógica.
- **R13** Proibido: `transactions/category` e `connections/disconnect` do mcp.ai; exclusão no Nibo; ferramentas MCP de enviar/pagar/apagar/aprovar.
- **Decisão 10/10:** gasto de viagem é **fato histórico**, decidido lançamento a lançamento; **não criar regra de viagem** (moeda, período, cidade).
- **Decisão 10/10:** o **Nibo está defasado**: `nota_fiscal.nibo_pago` nunca prova recebimento; recebimento real = crédito no extrato casado por valor.
- Ciclo de toda tarefa: teste vermelho (visto falhar pelo motivo certo) → mínimo → `pytest -q` e `npm test` verdes → doc → commit. Instalar com `sudo bash deploy/instalar.sh --confirmo-backup-exportado`.

## Review Focus

1. **Rodada que falha em silêncio** (a queda do mcp.ai em 09/10 passou horas sem ninguém saber): esperado, um aviso `rodada_parada` após 2 rodadas seguidas sem `conferida=1` (tarefa 4).
2. **Previsão que trata nota vencida e já paga como a receber:** esperado, nota com `nibo_pago=1` ou vencida há mais de 60 dias nunca entra na previsão, só na fila de conferência (tarefas 6 e 7).
3. **Aviso repetido a cada rodada (spam):** esperado, no máximo um aviso aberto por (tipo, chave) por dia (tarefa 4).
4. **Dado sensível em aviso ou em lote:** esperado, `aviso.payload` nunca contém CPF, conta ou chave PIX completos (tarefa 4).
5. **Backup que nunca foi restaurado fora da VPS:** esperado, o pacote semanal tem `integrity_check` e teste de restauração registrado em `rodada` (tarefa 11).

---

## Decisões e gates do Ricardo (só ele destrava; o plano marca onde cada um é usado)

| Gate | Decisão ou ação | Usado em |
|---|---|---|
| **G15** | Autorizar exceção à R2: mensagem de aviso **ao próprio Ricardo** (Telegram) | tarefa 5 |
| **G16** | XP Investimentos: reconectar no mcp.ai **ou** desligar a conta (`estado='nao'`) até 17/10 | tarefa 3 |
| **G17** | Backup fora da VPS: tarefa agendada na máquina local que puxa `/var/backups/gabi-brain/exportacao/` | tarefa 11 |
| **G18** | Primeiro lote do Nibo (escrita real): escolher 1 item, ler a confirmação, confirmar | tarefa 9 |
| **G19** | Subir ≥ 10 comprovantes reais de Pix no Paperless (ver tarefa 10) | tarefa 10 |
| **G20** | Aceitar a Fase 2 **sem** o item "pedido real pelo canal" (vai para o plano gabi-agent) | tarefa 13 |
| **G21** | Aprovar o corte do `gabi-financeiro` após 7 dias de paralelo sem divergência | tarefa 12 |

---

## Fase A — Fechar a Fase 1 (Dinheiro)

### Task 1: Medidor do aceite T1.14

**Files:**
- Create: `tools/aceite.py`
- Test: `tests/test_aceite.py`

**Interfaces:**
- Produces: `medir_fase1(con, hoje: date) -> dict` com chaves `dias_seguidos_conferidos: int`, `saldo_final_reprovado: int`, `classificado_pct: float` (categoria **e** para_quem preenchidos / total), `ultima_rodada_conferida: str | None`; `escrever_relatorio(resultado: dict, caminho: Path) -> None` (Markdown com cada critério, evidência e data).

- [ ] **Step 1: Write the failing tests** em `tests/test_aceite.py`: `test_conta_dias_seguidos_com_rodada_conferida_em_horario_de_brasilia`, `test_dia_sem_rodada_conferida_zera_a_sequencia`, `test_classificado_exige_categoria_e_para_quem`, `test_relatorio_lista_cada_criterio_com_data`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_aceite.py -v` — Expected: FAIL (módulo inexistente).
- [ ] **Step 3: Implement** `medir_fase1` lendo `rodada(fonte='open-finance', conferida=1)` agrupada por dia `America/Sao_Paulo`; sequência termina em `hoje`. CLI: `python -m tools.aceite --banco ... --saida docs/aceite-fase-1.md`.
- [ ] **Step 4: Run** os testes — Expected: PASS; depois `python -m tools.aceite` contra o banco real (somente leitura) deve imprimir `dias_seguidos_conferidos`.
- [ ] **Step 5: Commit** `git commit -m "feat: medidor do aceite T1.14"`.

### Task 2: Sugestões de regra por favorecido (PIX) para fechar 90% de categoria

**Files:**
- Create: `gabi/dinheiro/favorecidos.py`
- Modify: `gabi/dinheiro/classificar.py` (chamar o gerador em `classificar_pendentes`)
- Test: `tests/dinheiro/test_favorecidos.py`

**Interfaces:**
- Consumes: `regras.criar_sugestao(con, tipo, lancamento_id, payload, motivo) -> int`.
- Produces: `sugerir_por_favorecido(con, minimo: int = 3) -> int` (quantas sugestões novas). Sugestão `tipo='regra'`, `payload={"padrao": <favorecido>, "acao": {"categoria_id": ...}}` só quando o favorecido (descritivo `Pix enviado <NOME>`) tem `>= minimo` lançamentos **sem categoria** e todos os já categorizados com o mesmo favorecido têm a mesma categoria; nunca regra automática (R1).

- [ ] **Step 1: Write the failing tests**: `test_sugere_quando_favorecido_repete_com_categoria_unica`, `test_nao_sugere_se_categorias_divergem`, `test_nao_duplica_sugestao_pendente`, `test_nao_sugere_para_favorecido_com_menos_de_minimo`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/dinheiro/test_favorecidos.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `sugerir_por_favorecido` (agrupa `descricao_original like 'Pix enviado %'`); chamar no fim de `classificar_pendentes`.
- [ ] **Step 4: Run** `.venv/bin/pytest -q tests/dinheiro` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: sugestões de regra por favorecido de PIX"`.
- [ ] **Step 6 (Ricardo, sem código):** aprovar as sugestões na tela Regras. Meta: `classificado_pct >= 0.90` pela tarefa 1.

### Task 3: XP Investimentos fora do caminho da conferência (G16)

**Files:** nenhum código novo; **Modify** `docs/issues/0001-bancos-indisponiveis-c6-xp.md`.

- [ ] **Step 1 (Ricardo, G16):** reconectar a XP Investimentos no mcp.ai **ou** responder "desligar". Prazo 17/10.
- [ ] **Step 2:** se reconectou: `sudo systemctl start gabi-brain-extratos` e conferir `conta_estado.ult_sync_ok` da conta 10 não nulo; fechar a issue com a data. Se desligou: `PATCH /api/v1/cadastros/contas/10 {"estado":"nao"}` e registrar na issue.
- [ ] **Step 3: Commit** `git commit -m "docs: issue 0001 resolvida (XP)"`.

### Task 4: Produtor de avisos (`aviso`) — falhas, atrasos e cancelamentos

**Files:**
- Create: `gabi/avisos.py`, `deploy/gabi-brain-avisos.service`, `deploy/gabi-brain-avisos.timer`
- Modify: `deploy/instalar.sh` (instalar e habilitar o timer), `tests/test_deploy.py`
- Test: `tests/test_avisos.py`

**Interfaces:**
- Produces: `gerar_avisos(con, agora: datetime) -> list[int]` (ids de `aviso` criados) para os tipos `rodada_parada` (2 rodadas `open-finance` seguidas com `conferida=0`, ou `dados_ate` > 3 dias), `conta_atrasada` (compromisso `atrasado` há > 1 dia), `cobrada_apos_cancelar` (assinatura `status='cancelar'` com débito depois de `status_em`), `vence_hoje` (compromissos do dia, resumo único). Idempotente: no máximo um aviso **aberto** por `(tipo, chave)` por dia; `payload` só com nome do compromisso, valor, vencimento e id (nunca CPF, conta ou chave PIX).
- Timer a cada 15 min; falha do próprio serviço grava `aviso` `servico_falhou` via `OnFailure=`.

- [ ] **Step 1: Write the failing tests**: `test_rodada_parada_depois_de_duas_nao_conferidas`, `test_nao_duplica_aviso_aberto_no_mesmo_dia`, `test_cobrada_apos_cancelar_gera_aviso`, `test_payload_nao_tem_dado_sensivel`, `test_vence_hoje_agrupa_em_um_aviso`; em `tests/test_deploy.py`: `test_timer_de_avisos_instalado_e_habilitado`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_avisos.py tests/test_deploy.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `gerar_avisos` e a unit (`User=gabibrain`, sandbox como `gabi-brain-saldos.service`, `OnFailure=` com o serviço de aviso).
- [ ] **Step 4: Run** a suíte inteira — Expected: PASS. Instalar e conferir `select tipo, count(*) from aviso group by 1`.
- [ ] **Step 5: Commit** `git commit -m "feat: produtor de avisos (rodada parada, atraso, cancelada cobrada)"`.

### Task 5: Entrega dos avisos ao Ricardo (G15)

**Files:**
- Create: `painel/src/componentes/Avisos.tsx`; **Modify** `gabi/rotas/contagens.py` (contador de avisos abertos), `gabi/rotas/cobrar.py` ou nova rota `GET/POST /api/v1/avisos`
- Test: `tests/rotas/test_avisos_api.py`, `painel/tests/avisos.test.tsx`

**Interfaces:**
- Consumes: `aviso(id, tipo, payload, criado_em, entregue_em)`.
- Produces: `GET /api/v1/avisos` (abertos, mais novos primeiro) e `POST /api/v1/avisos/{id}/lido` (marca `entregue_em`); sino no painel com contador.

- [ ] **Step 1: Write the failing tests**: `test_lista_so_avisos_abertos_do_boss`, `test_marcar_lido_registra_entregue_em_e_e_idempotente`; vitest `mostra contador e o texto do aviso`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** a rota e o componente (painel, sempre disponível, sem G15).
- [ ] **Step 4: Run** `pytest -q` e `npm test` — Expected: PASS; regenerar amostras e `docs/api.md` (`python -m tools.gerar_amostras && python -m tools.gerar_docs_api`).
- [ ] **Step 5: Commit.**
- [ ] **Step 6 (só se G15 aprovado):** `tools/entregar_avisos.py` lê `aviso` abertos e envia pelo canal já existente do Ricardo; `test_entrega_so_marca_entregue_apos_confirmacao_do_canal` (mesmo critério do TC.3 do plano mestre). Sem G15, a entrega é o painel; o envio completo fica no plano gabi-agent.

---

## Fase B — Fechar a Fase 2 (Cobrar) e a previsão de caixa

### Task 6: Saldo projetado (entradas e saídas)

**Files:**
- Create: `gabi/dinheiro/projecao.py`
- Modify: `gabi/rotas/dinheiro.py` (rota `GET /api/v1/caixa/projecao?dias=30`)
- Test: `tests/dinheiro/test_projecao.py`, `tests/rotas/test_dinheiro_api.py`

**Interfaces:**
- Consumes: `contas_pagar.caixa_unico(con, em)`, `contas_pagar.faturas_abertas(con, em)`, `cobrar.previsao.previsao(con, hoje, meses)`, tabela `compromisso`.
- Produces: `projetar(con, hoje: date, dias: int = 30) -> list[dict]` com `{"dia", "entradas_centavos", "saidas_centavos", "saldo_centavos"}` por dia; saldo inicial = `caixa_unico`; saídas = compromissos `aberto|atrasado|previsto` + faturas abertas (sem contar o que a regra de débito já pago exclui); entradas = **só** `previsao.a_vencer` e `projetado` (nunca `a_confirmar` nem `antigas`).

- [ ] **Step 1: Write the failing tests**: `test_saldo_inicial_e_o_caixa_unico`, `test_saida_de_fatura_aberta_entra_no_vencimento`, `test_nota_vencida_e_nao_baixada_nao_entra_como_entrada`, `test_compromisso_pago_nao_reduz_o_saldo`, `test_valor_em_centavos_inteiros`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/dinheiro/test_projecao.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `projetar` e a rota (valores como string decimal, R7).
- [ ] **Step 4: Run** a suíte — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: saldo projetado do caixa"`.

### Task 7: Tela "Previsão" e "Notas a receber"

**Files:**
- Create: `painel/src/telas/Caixa/Projecao.tsx`, `painel/src/telas/Cobrar/NotasAReceber.tsx`, `deploy/gabi-brain-notas.timer` (diário 06:40 BRT, aciona o `gabi-brain-notas.service` já existente); **Modify** `painel/src/navegacao.ts`, `gabi/rotas/cobrar.py` (rota `GET /api/v1/cobrar/notas`), `deploy/instalar.sh`
- Test: `painel/tests/projecao.test.tsx`, `painel/tests/notas.test.tsx`, `tests/rotas/test_cobrar_api.py`, `tests/test_deploy.py`

**Interfaces:**
- Consumes: `GET /api/v1/caixa/projecao`, `GET /api/v1/cobrar/previsao`, tabela `nota_fiscal`.
- Produces: `GET /api/v1/cobrar/notas?status=autorizada&aberta=1` (número, tomador, emissão, vencimento, bruto, líquido, `nibo_pago`, PDF/XML disponível).

- [ ] **Step 1: Write the failing tests**: pytest `test_notas_lista_so_autorizadas_em_aberto_e_formata_valores`; vitest `projecao mostra o saldo por dia e separa a fila de conferência`, `notas a receber marca "Nibo diz pago" sem tratá-lo como recebido`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** rota e telas com as classes do sistema Industry (R17, sem reinterpretar).
- [ ] **Step 4: Run** `pytest -q`, `npm test`, `npm run build` — Expected: PASS.
- [ ] **Step 5:** `test_timer_de_notas_instalado_e_habilitado` em `tests/test_deploy.py` (vermelho antes de criar o timer), depois criar o timer e instalar; conferir `systemctl list-timers 'gabi-brain-notas*'`.
- [ ] **Step 6: Commit.** Gerar capturas (`python -m tools.capturas`) para o G14 da Fase 2.

### Task 8: Casamento de recebimentos com notas (proposto → confirmado)

**Files:**
- Create: `migrations/0014_recebimento_nota.sql`, `gabi/cobrar/recebimentos.py`
- Modify: `gabi/rotas/cobrar.py` (confirmar/rejeitar)
- Test: `tests/cobrar/test_recebimentos.py`

**Interfaces:**
- Produces: tabela `recebimento_nota(id, nota_id, lancamento_id, confianca REAL, motivo, estado CHECK IN ('proposto','confirmado','rejeitado'))`; `propor_recebimentos(con) -> int`: crédito (`valor_centavos > 0`) em conta `pj=1`, valor igual ao `valor_liquido_centavos` da nota **autorizada** com vencimento até 90 dias antes, tomador no descritivo (CNPJ ou nome); confiança como em `comprovantes._propor`. Só propõe; **confirmar é do Ricardo** (R1).

- [ ] **Step 1: Write the failing tests**: `test_propoe_credito_com_valor_liquido_igual`, `test_nunca_vira_confirmado_sozinho`, `test_nao_propoe_para_nota_negada_ou_cancelada`, `test_dois_creditos_iguais_geram_duas_propostas_sem_duplicar`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/cobrar/test_recebimentos.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** a migração (0013 e anteriores congeladas) e `propor_recebimentos`; chamar depois de cada rodada de extratos.
- [ ] **Step 4: Run** a suíte — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat: proposta de recebimento de nota por crédito no extrato"`.

### Task 9: Primeiro lote do Nibo em conta real (G18)

**Files:** `docs/historico/aceite-fase-2.md` (evidência); código só se o formato de resposta do Nibo divergir.

- [ ] **Step 1 (Ricardo, G18):** escolher 1 item de reembolso com comprovante; ler o `texto_confirmacao` do `GET /api/v1/cobrar/reembolsos`; confirmar na tela.
- [ ] **Step 2:** conferir o agendamento no Nibo e o anexo; **rodar o lote de novo** e conferir que **não duplicou** (`reference gabi:<id>`).
- [ ] **Step 3:** se o Nibo responder em formato diferente do suposto (`scheduleId`, `fileId`, rota de baixa), escrever o teste vermelho com a resposta real em `tests/cobrar/test_nibo_escrita.py`, ajustar `gabi/fontes/nibo_escrita.py` e commitar.
- [ ] **Step 4:** registrar a evidência em `docs/historico/aceite-fase-2.md`.

### Task 10: Ingestão de comprovantes do Paperless (só com dado real, G19)

**Files:**
- Create: `gabi/cobrar/ingestao.py`, `tests/cobrar/test_ingestao.py`; **Modify** `deploy/` (timer diário)

**Interfaces:**
- Consumes: `Paperless.docs()`, `extrator.tipo_documento`, `extrator.ler_comprovante_pix`, `comprovantes.registrar_comprovante`, `comprovantes.propor_vinculos`.
- Produces: `ingerir(con, paperless, hoje) -> ResumoIngestao(lidos, novos, sem_valor)`; idempotente por `paperless_id`; etiqueta o documento `gabi:comprovante` (só acrescenta, R10).

- [ ] **Step 1 (Ricardo, G19):** subir ≥ 10 comprovantes reais de Pix. **Não escrever o job antes**: o Paperless de hoje (215 docs) não tem nenhum (os 2 "comprovante_pix" são um relatório jurídico).
- [ ] **Step 2: Write the failing tests** com 3 comprovantes reais anonimizados: `test_le_valor_data_e_cnpj_do_comprovante_real`, `test_ingestao_e_idempotente`, `test_documento_sem_valor_nao_vira_comprovante`.
- [ ] **Step 3: Implement** `ingerir` e ligar ao `propor_vinculos`.
- [ ] **Step 4: Run** — Expected: PASS; medir `select 1.0*sum(estado='confirmado' or confianca>=0.9)/count(*)` ≥ 0,80 (T2.10).
- [ ] **Step 5: Commit.**

### Task 11: Backup fora da VPS e teste de restauração

**Files:**
- Create: `deploy/gabi-brain-exportacao.service`, `deploy/gabi-brain-exportacao.timer`, `docs/runbook.md` (seção "Backup fora da VPS")
- Test: `tests/test_deploy.py`, `tests/test_backup_banco.py`

**Interfaces:**
- Consumes: `gabi.backup.backup_db`, `testar_restauracao`.
- Produces: pacote semanal `/var/backups/gabi-brain/exportacao/gabi-brain-AAAA-MM-DD.sqlite.gpg` (criptografado; chave pública do Ricardo em `/etc/gabi/backup.pub`, colocada por ele) mais uma linha `rodada(fonte='exportacao')`.

- [ ] **Step 1: Write the failing tests**: `test_exportacao_gera_pacote_criptografado_e_registra_rodada`, `test_exportacao_falha_se_restauracao_falha`, `test_timer_de_exportacao_semanal_instalado`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** a unit e o passo de criptografia com `gpg --encrypt --recipient-file`.
- [ ] **Step 4: Run** a suíte — Expected: PASS.
- [ ] **Step 5 (Ricardo, G17):** criar a tarefa na máquina local que puxa o diretório; conferir o hash de um pacote e registrar a data no runbook.
- [ ] **Step 6: Commit.**

---

## Fase C — Virada, aceite e documentação

### Task 12: Virada do `gabi-financeiro` (G21)

**Files:**
- Create: `tools/comparar_agenda.py`, `tests/test_comparar_agenda.py`

**Interfaces:**
- Produces: `comparar(brain_con, compromissos_json: Path, mes: str) -> list[dict]` com `{"linha", "so_no_brain", "so_no_financeiro", "valor_diferente"}`; saída vazia por 7 dias seguidos é o critério de corte.

- [ ] **Step 1: Write the failing tests**: `test_igual_nao_gera_divergencia`, `test_linha_so_de_um_lado_e_reportada`, `test_valor_diferente_e_reportado_com_os_dois_valores`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** lendo `/var/lib/gabi-fin/compromissos.json` (somente leitura) e `compromisso` do brain.
- [ ] **Step 4:** rodar por 7 dias (ver `aviso`/relatório diário); divergência vira ajuste de cadastro, não de código.
- [ ] **Step 5 (Ricardo, G21):** aprovar o corte; então `python -m tools.congelar --confirm` (de `gabi-brain-migracao`; reversível) para os timers `gabi-*` do financeiro.
- [ ] **Step 6: Commit.**

### Task 13: Aceites e dívidas pequenas

**Files:** `docs/aceite-fase-1.md`, `docs/historico/aceite-fase-2.md`; **Modify** `gabi/cobrar/` (dívidas do ledger).

- [ ] **Step 1:** rodar `python -m tools.aceite` (tarefa 1) quando houver 7 rodadas seguidas conferidas (≈ 16/10) e `classificado_pct >= 0.90`; commitar `docs/aceite-fase-1.md`.
- [ ] **Step 2 (G20):** escrever `docs/historico/aceite-fase-2.md` com os 3 itens do T2.10; o item "pedido real pelo canal" fica **adiado para o plano gabi-agent**, por decisão do Ricardo.
- [ ] **Step 3: Dívidas** (cada uma com teste): unificar `_brl`/`_agora` duplicados em 5 módulos de `gabi/cobrar`; "Marcar como cobrado" respeitar os itens selecionados e ligar-se ao rascunho; `extrator.tipo_documento(texto, hoje)` receber a data (hoje usa `date.today()`).
- [ ] **Step 4: Commit.**

### Task 14: Documentação e encerramento

**Files:**
- Modify: `/home/ricardo/handoff/docs/superpowers/plans/2026-10-08-gabi-brain-plano-mestre.md` (marcar as tarefas feitas e retirar o bloco CANAL para o plano gabi-agent), `docs/historico/TRILHA.md`, `docs/STATUS.md`, `docs/runbook.md`, `docs/ARQUITETURA.md`
- Create: `docs/adr/010-donos-padrao-e-origem-fonte.md`, `docs/adr/011-favorecido-nao-e-para-quem.md`, `docs/adr/012-nfse-previsao-e-nibo-defasado.md` (≤ 15 linhas cada: Contexto · Decisão · Consequência · Quando reverter)

- [ ] **Step 1:** atualizar plano mestre, TRILHA e STATUS com o que foi feito entre 09 e 10/10 e com este plano.
- [ ] **Step 2:** runbook: como aplicar donos (`sudo ~/aplicar-donos.sh`), rodar a rodada, importar notas, restaurar backup, ler avisos.
- [ ] **Step 3:** as 3 ADRs.
- [ ] **Step 4: Commit** e marcar a versão: `git tag v1.0-gabi-brain` (só depois de G20 e dos dois aceites).

---

## Fora do escopo (decidido)

- **Fase 3 (Trabalho):** congelada. Reabrir quando: classificação em dia, 7 rodadas conferidas, previsão de caixa em uso, G11/G12 resolvidos.
- **Fase 4:** só por pedido do Ricardo.
- **Agente de canal (Hermes), identidade por remetente, WhatsApp, desligar o OpenClaw:** plano próprio `gabi-agent`, depois deste.
- **Regras com condição de viagem (moeda, período, cidade):** recusadas por decisão do Ricardo em 10/10.

## Ordem sugerida e dependências

1 → 2 (paralelo com 3) → 4 → 5 → 6 → 7 → 8 → 11 → 12; as tarefas 9 e 10 dependem de G18/G19 e entram quando o Ricardo liberar; 13 e 14 fecham. Tarefas 1, 4, 6, 7, 8 e 11 são independentes entre si no código (sem interface compartilhada além do banco).
