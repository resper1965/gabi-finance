# Arrumação pós-Hermes (26/10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os 4 itens recomendados em 26/10 sem abrir recurso novo: (1) dois bloqueios de dado na correção de Documentos, (2) e-mail de remetente do sistema nunca vira alerta emergencial, (3) vigia semanal de saúde sem LLM, (4) timers de Teams e agenda menos frequentes + BACKLOG em dia.

**Architecture:** Mudanças pequenas em módulos existentes (`gabi/documentos/repositorio.py`, `gabi/correio/{regras,fontes,processar}.py`, `deploy/*.timer`). O vigia é um script `no_agent` do cron do Hermes (mesmo padrão de `~/.hermes/scripts/agenda_financeira.py`), versionado em `deploy/hermes/scripts/vigia_semanal.py`; nenhuma tabela, timer ou ADR novo no brain.

**Tech Stack:** Python 3 (sqlite3, FastAPI), pytest, systemd timers, cron do Hermes.

**Spec:** recomendação aprovada no chat de 26/10 (itens 1 a 4). Item "congelar rodada de contatos" foi retirado: `contatos_propostas.gerar` roda dentro da sincronização (`gabi/contatos/contatos.py:215`), é barata e congelá-la exige código novo sem ganho.

## Global Constraints
- Branch `feat/arrumacao-26-10` em worktree `~/gabi-brain-arrumacao`, base `main`.
- Sem migração nova; dados nunca chumbados (a lista de remetentes do sistema é parâmetro `email.remetentes_sistema`, editável por `PUT /api/v1/correio/parametros`, padrão `[]`).
- Erros de Documentos nunca levam número nem texto do documento (só código fixo).
- Merge e instalação só com autorização do Ricardo.
- Suíte: `.venv/bin/python -m pytest -q` (ler o resumo, não o exit code).

## Review Focus
- Correção que só corrige o VALOR do principal (OCR errado) continua aprovando (não confundir com "remover o principal").
- Correção sem a chave `numeros` (só datas ou titular) não é afetada pelos bloqueios.
- Remetente do sistema classificado `emergencial` numa retomada (classe já gravada) também é rebaixado.
- `email.remetentes_sistema` com lixo no banco (não-lista, JSON inválido) não derruba a rodada (trata como vazio).
- Vigia: brain fora do ar ou token ausente vira uma linha "Falhou" e exit 1, nunca traceback.

---

### Task 1: Documentos — bloquear "principal removido" e "correção sem número"

**Files:**
- Modify: `gabi/documentos/repositorio.py` (`decidir`)
- Modify: `gabi/rotas/documentos.py` (`MENSAGENS`)
- Test: `tests/documentos/test_repositorio.py`

**Interfaces:**
- Produces: `ErroDocumentos("numero_obrigatorio")` e `ErroDocumentos("principal_removido")`; rota responde 400 com mensagens "o documento precisa de ao menos um número" e "o número principal não pode ser removido; corrija o valor dele".

Regras (só quando `estado == "aprovada"` e `"numeros" in campos`, depois de `_sem_vazios`):
- `campos["numeros"] == []` → `numero_obrigatorio`.
- Proposta original tinha números e o novo `numeros[0]` tem `chave()` igual à de um número SECUNDÁRIO original (índice ≥ 1) e diferente da do principal original → `principal_removido`.

- [ ] **Step 1: testes que falham** — `test_correcao_sem_numero_recusa`, `test_correcao_que_remove_principal_recusa` (proposta com números [A principal, B secundário]; correção `numeros=[B]` → `principal_removido`, proposta segue `pendente`, documento ativo inalterado), `test_correcao_do_valor_do_principal_aprova` (`numeros=[A', B]` aprova), `test_correcao_sem_chave_numeros_inalterada`; teste de rota com status 400 e código.
- [ ] **Step 2:** rodar `pytest tests/documentos -q` → falham.
- [ ] **Step 3:** implementar no `decidir` antes de `validar`, dentro da transação (nada muda se recusar).
- [ ] **Step 4:** `pytest tests/documentos tests/test_rotas_documentos*.py -q` → passam.
- [ ] **Step 5:** commit `fix(documentos): correção não remove o número principal nem aprova sem número`.

### Task 2: E-mail — remetente do sistema nunca é emergencial

**Files:**
- Modify: `gabi/correio/regras.py` (extrair o casamento endereço/domínio de `regra_lixo` para `_casa(con, chave_parametro, remetente) -> str | None`; nova `remetente_sistema(con, remetente) -> str | None` sobre `email.remetentes_sistema`)
- Modify: `gabi/correio/fontes.py` (`PADROES["remetentes_sistema"] = []`, validação igual à de `regras_lixo`, máx. 200)
- Modify: `gabi/correio/processar.py` (depois de obter `classe`, nova ou retomada: se `emergencial` e `remetente_sistema` → `Classe("importante", classe.prioridade, "remetente do sistema", classe.confianca)` gravada na linha; segue o fluxo normal sem alerta)
- Modify: `docs/runbook.md#correio` (uma linha sobre o parâmetro)
- Test: `tests/correio/test_regras.py`, `tests/correio/test_processar.py`, teste de parâmetros

- [ ] **Step 1: testes que falham** — `test_remetente_sistema_endereco_e_dominio`, `test_remetente_sistema_parametro_invalido_e_vazio`, `test_emergencial_de_remetente_sistema_vira_importante_sem_aviso` (nenhum `aviso` `email_emergencial`, `classe='importante'`, `estado='classificada'`), `test_retomada_emergencial_de_sistema_rebaixada`, `test_parametro_remetentes_sistema_valida`.
- [ ] **Step 2:** rodar → falham.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** `pytest tests/correio -q` → passam; `regra_lixo` com os testes antigos intactos.
- [ ] **Step 5:** commit `feat(correio): remetentes do sistema nunca disparam alerta emergencial`.

### Task 3: Vigia semanal (cron `no_agent` do Hermes) + promessas da Onda 3

**Files:**
- Create: `deploy/hermes/scripts/vigia_semanal.py`
- Modify: `tools/auditar_promessas.py` (`ESCRITAS` ganha `financeiro_registrar_a_receber`, `financeiro_cancelar_a_receber`, `email_lixeira`, `email_regra_lixo`, `email_remover_regra_lixo`, `familia_registrar_*` já estão)
- Modify: `docs/runbook.md` (seção `#vigia`: copiar o script para `~/.hermes/scripts/` e criar o job `vigia-semanal`, `0 9 * * 1`, `no_agent`, entrega `telegram`)
- Test: `tests/test_vigia_semanal.py` (carrega o script por `importlib` a partir do caminho)

**Interfaces:**
- `units_falhando(saida_systemctl: str) -> list[str]`: nomes `gabi-brain-*` e `hermes-*` da saída de `systemctl --failed --plain --no-legend` (ignora o resto).
- `fontes_paradas(envelope: dict) -> list[str]`: nomes das `fontes` com `estado` fora de `("ok", "em_espera")`.
- `promessas(saida: str) -> int | None`: lê "N casos" da última linha do `auditar_promessas`.
- `texto(units, paradas, casos) -> str`: tudo zero → `"Vigia semanal: tudo ok (serviços no ar, dados em dia, 0 promessas sem escrita)."`; senão uma linha por problema, prefixo `"Vigia semanal:"`.
- `main(argv) -> int`: chama `avisos_abertos` (dias=1) pelo MCP como `agenda_financeira.py` (token de `~/.hermes/.env`), `systemctl`, e `~/gabi-brain/.venv/bin/python -m tools.auditar_promessas` (cwd `~/gabi-brain`); qualquer exceção → `"Falhou: vigia semanal (<Tipo>)"`, return 1.

- [ ] **Step 1: testes que falham** — um por função acima, incluindo `test_ignora_unit_alheia` (`systemd-networkd-wait-online.service` fora) e `test_main_sem_token_falha_curto`.
- [ ] **Step 2:** rodar → falham.
- [ ] **Step 3:** implementar (só stdlib).
- [ ] **Step 4:** `pytest tests/test_vigia_semanal.py tests/test_auditar_promessas.py -q` → passam.
- [ ] **Step 5:** commit `feat(hermes): vigia semanal sem LLM e promessas da Onda 3 no auditor`.

### Task 4: Timers mais leves + BACKLOG em dia

**Files:**
- Modify: `deploy/gabi-brain-teams.timer` (`OnCalendar=*-*-* 07..20:00/15:00 America/Sao_Paulo`, descrição "a cada 15 min")
- Modify: `deploy/gabi-brain-agenda.timer` (`OnCalendar=*-*-* 06..22:10,40:00 America/Sao_Paulo`, "a cada 30 min")
- Modify: `docs/runbook.md` (frequências citadas), `docs/BACKLOG.md` (DOC1 sai de "Aberto": instalado 25/10; item de Documentos e de alerta do sistema saem de "Depois"; vigia e timers registrados)
- Test: os testes que conferem timers (`grep -rn "OnCalendar" tests`) ajustados se existirem; `systemd-analyze calendar` nas duas expressões.

- [ ] **Step 1:** editar timers; `systemd-analyze calendar '<expr>'` → válido.
- [ ] **Step 2:** conferir os prazos de frescor (`agenda` 12 h, `teams` None) — nada a mudar.
- [ ] **Step 3:** docs e BACKLOG.
- [ ] **Step 4:** suíte inteira `pytest -q` (ler resumo) + `cd painel && npx vitest run`.
- [ ] **Step 5:** commit `chore: timers de Teams (15 min) e agenda (30 min); BACKLOG em dia`.

### Fecho
- Revisão final do branch por um revisor novo; corrigir o que for real.
- Pedir ao Ricardo autorização para merge + `sudo ~/instalar-brain.sh` (copia timers e reinicia API/MCP), `systemctl daemon-reload`, e criar o job do vigia; `PUT email.remetentes_sistema` com a lista que eu levantar dos e-mails emergenciais vindos do sistema (ele confirma).
