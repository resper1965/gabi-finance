# Projetos no Linear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Projeto, etapas e prazos passam a morar no Linear (Hermes fala com o MCP oficial); o brain guarda só a pasta (dinheiro, fatos, anexos, documentos, pessoas) ligada por `linear_id`.

**Architecture:** Migração 0089 acrescenta `projeto.linear_id`/`linear_url`; nova ferramenta MCP `projeto_ligar` registra a pasta; `projeto_criar` e os parâmetros `projeto`/`depois_de`/`marco` de `atividade_*` saem do que o Hermes enxerga (código fica); painel vira pasta; `projeto_parado` ignora falta de atividade quando há `linear_id`; SOUL e docs explicam a fronteira. Nada é instalado: o `mcp_servers.linear` do Hermes é passo de instalação (runbook `#linear`).

**Tech Stack:** Python/FastAPI/SQLite, MCP (FastMCP), React/TS (painel), pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-projetos-no-linear-design.md` (ADR-038: `docs/adr/038-projetos-no-linear.md`)

## Global Constraints

- Branch própria `feat/projetos-linear`; nada instalado, nada mergeado, sem push sem ok do Ricardo.
- Migração só acrescenta colunas; nenhuma migração de dados ("Trocar Lâmpadas", id 1, fica sem `linear_id`).
- Sem sincronização em nenhum sentido; Linear fora do ar = Hermes avisa e para (sem plano B no brain).
- Permanecem no include: `projeto_gasto`, `projeto_fato`, `projeto_fatos`, `projeto_pessoa`, `projeto_anexar`, `anexo_recentes`, `projeto_atualizar`, `projeto_listar`, `projeto_ver`. Saem: `projeto_criar` e os parâmetros `projeto`, `depois_de`, `marco` de `atividade_criar` e `atividade_listar`. Entra: `projeto_ligar`.
- `projeto_ligar` só depois do sim; idempotente por `linear_id`; nunca a partir de texto de e-mail/Teams/documento/terceiro.
- Include do Hermes é explícito e testado: regerar com `python -m tools.gerar_hermes`.
- Privacidade é do Ricardo: não mascarar dado.

## Review Focus

- `linear_id` repetido em dois projetos diferentes: o banco recusa (unicidade só quando preenchido).
- `projeto_ligar` com `linear_id` já ligado: devolve o mesmo projeto, sem duplicar nem sobrescrever o nome.
- `projeto_ligar` com projeto existente (por id/nome) já ligado a outro `linear_id`: recusa com `requisicao_invalida`.
- Projeto concluído/cancelado: `projeto_ligar` não liga.
- `linear_id`/`linear_url` vazios ou só espaços: recusa; `linear_url` que não começa com `https://`: recusa.
- `projeto_parado` de projeto com `linear_id` e só atividade antiga: não avisa; fato/anexo novo continuam contando para os sem `linear_id`.

---

### Task 1: Migração 0089 e regra `projetos.ligar`

**Files:**
- Create: `migrations/0089_projeto_linear.sql`
- Modify: `gabi/projetos.py` (`_item`, `ver`, `listar` devolvem `linear_id`/`linear_url`; nova `ligar`; `parados`/`_ultimo_movimento`)
- Test: `tests/test_projetos_linear.py`, ajustar `tests/test_esquema.py` se contar migrações

**Interfaces:**
- Produces: `projetos.ligar(con, agora, quem, origem, linear_id: str, linear_url: str, nome: str = "", projeto_id: int | None = None) -> dict` (devolve `projetos.ver`; cria a pasta se `projeto_id` é None, exigindo `nome`; liga existente caso contrário). `ValueError` para dado inválido; `LookupError` para id inexistente. `_item` e `ver` ganham as chaves `linear_id` e `linear_url` (None quando não ligado).

- [ ] **Step 1: Escrever testes que falham** em `tests/test_projetos_linear.py` (fixture `con` como em `tests/test_projetos_avisos.py`): `test_migracao_acrescenta_colunas` (colunas existem, `linear_id` único: segundo insert igual levanta `sqlite3.IntegrityError`, dois NULL passam); `test_ligar_cria_pasta` (`ligar(..., "LIN-1", "https://linear.app/x/project/fazenda", nome="Vender a fazenda")` → `ver` com `linear_id=="LIN-1"`, `status=="ativo"`, decisão gravada); `test_ligar_idempotente_por_linear_id` (segunda chamada devolve mesmo `id`, uma só linha); `test_ligar_projeto_existente` (projeto_id de um projeto sem link vira ligado); `test_ligar_recusa_existente_ja_ligado_a_outro_id`; `test_ligar_recusa_final` (cancelado); `test_ligar_valida` (`linear_id` vazio/branco, URL sem `https://`, sem nome ao criar → `ValueError`); `test_parado_com_linear_id_ignora_atividade` (projeto ligado, atividade concluída recente: `parados` conta só criação/fato/anexo; projeto sem `linear_id` mantém comportamento atual).
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/pytest tests/test_projetos_linear.py -q` → FAIL (coluna/`ligar` inexistentes).
- [ ] **Step 3: Escrever `migrations/0089_projeto_linear.sql`** com cabeçalho (spec, desfazer: `alter table projeto drop column linear_url; drop index projeto_linear_id; alter table projeto drop column linear_id; delete from schema_versao where nome='0089_projeto_linear.sql';`), `alter table projeto add column linear_id text`, `add column linear_url text`, `create unique index projeto_linear_id on projeto(linear_id) where linear_id is not null`.
- [ ] **Step 4: Implementar** `ligar` em `gabi/projetos.py` (savepoint como `criar`, `_auditar` com "projeto N ligado ao Linear: <linear_id>"), expor as chaves em `_item`/`ver`, e em `_ultimo_movimento` pular o select de `atividade` quando `projeto.linear_id` não é nulo (passar a linha/flag a partir de `parados` e `revalidar_aviso`).
- [ ] **Step 5: Rodar** `.venv/bin/pytest tests/test_projetos_linear.py tests/test_projetos.py tests/test_projetos_avisos.py tests/test_esquema.py -q` → tudo PASS (ler o resumo, não o exit code).
- [ ] **Step 6: Commit** `feat(projetos): migração 0089 e projetos.ligar (ADR-038)`.

### Task 2: Ferramenta MCP `projeto_ligar` e limpeza do que o Hermes vê

**Files:**
- Modify: `gabi/mcp/ferramentas_projetos.py` (nova ferramenta, `NOMES`, `FORA_DO_HERMES`), `gabi/mcp/ferramentas_atividades.py` (tirar `projeto`, `depois_de`, `marco` da assinatura registrada de `atividade_criar` e `atividade_listar` e das descrições; funções `atividade_criar`/`atividade_listar` de módulo mantêm os parâmetros), `gabi/mcp/servidor.py` (`ferramentas_do_hermes()`; instrução do servidor na linha ~122 cita `projeto_ligar`), `tools/gerar_hermes.py`, `docs/fontes/hermes.md` (regerar), `docs/api.md`/`docs/openapi.json` se o gerador existente os cobrir
- Test: `tests/mcp/test_projetos_mcp.py`, `tests/mcp/test_hermes.py`, `tests/mcp/test_servidor.py`

**Interfaces:**
- Consumes: `projetos.ligar` (Task 1).
- Produces: ferramenta `projeto_ligar(projeto: str = "", linear_id: str, linear_url: str, nome: str = "")` (escopo `projetos`; `projeto` = id/trecho do nome de pasta existente, vazio = cria); `ferramentas_projetos.FORA_DO_HERMES = ("projeto_criar",)`; `servidor.ferramentas_do_hermes() -> list[str]` = `ferramentas_do_token(ESCOPOS_HERMES)` sem `FORA_DO_HERMES`. `projeto_listar`/`projeto_ver` devolvem `linear_url` (via Task 1).

- [ ] **Step 1: Testes que falham:** em `test_projetos_mcp.py`: `test_projeto_ligar_cria_e_e_idempotente` (duas chamadas, `linear_id` igual → mesmo `id`, `projeto_ver` traz `linear_url`); `test_projeto_ligar_liga_existente_por_nome`; `test_projeto_ligar_erros` (`linear_id` vazio → `requisicao_invalida`; projeto inexistente → `nao_encontrado`; ambíguo → `ambiguo`). Em `test_hermes.py`: include == `ferramentas_do_hermes()`, contém `projeto_ligar`, não contém `projeto_criar`; atualizar `test_soul_ensina_os_projetos…` na Task 3. Em `test_servidor.py`: contagem de `ESCOPOS_FERRAMENTAS` passa a 76 (renomear o teste mantendo o sentido) e `atividade_criar`/`atividade_listar` registradas não aceitam `projeto`, `depois_de`, `marco` (chamar com `projeto="x"` falha na validação do esquema).
- [ ] **Step 2: Rodar** `.venv/bin/pytest tests/mcp -q -x` → FAIL esperado nos novos.
- [ ] **Step 3: Implementar** `projeto_ligar` (função `projeto_ligar(con, agora, projeto="", linear_id="", linear_url="", nome="")` + registro com docstring: só depois do sim, o que grava, idempotência), incluir em `NOMES`; `FORA_DO_HERMES`; `ferramentas_do_hermes()`; ajustar `gerar_hermes.lista_atual` e `test_hermes` para usá-la; reduzir assinaturas registradas de `atividade_*`; rodar `python -m tools.gerar_hermes`.
- [ ] **Step 4: Rodar** `.venv/bin/pytest tests/mcp tests/test_docs_api.py -q` → PASS (se `docs/api.md`/`openapi.json` divergirem, regerar pelo comando que `test_docs_api.py` indica).
- [ ] **Step 5: Commit** `feat(mcp): projeto_ligar; projeto_criar e dependência/marco fora do Hermes`.

### Task 3: SOUL com a fronteira Linear/brain

**Files:**
- Modify: `deploy/hermes/SOUL.md` (linhas de projetos: exceção ~8, "Onde achar" ~42–46, ~58, ajuda ~98), `tests/mcp/test_hermes.py`

**Interfaces:**
- Consumes: `projeto_ligar` (Task 2); ferramentas do Linear referidas por descrição ("as ferramentas do Linear", sem nomes exatos: conferidos na instalação).
- Produces: regras no SOUL: parte de projeto → Linear; solto → brain; nunca nos dois; cria no Linear só depois do sim, depois `projeto_ligar` (também após o sim); "como está X?" junta etapas (Linear) e `projeto_ver`; Linear fora do ar → avisa e para, sem plano B no brain; etapa do Ricardo atribuída a ele no Linear.

- [ ] **Step 1: Reescrever** `test_soul_ensina_os_projetos_e_so_grava_depois_do_sim` para exigir: `projeto_ligar` na exceção e em "Onde achar"; `projeto_criar` ausente do SOUL; frases-chave "Linear", "depois do sim", "nunca nos dois", "Linear fora do ar" ("avisa" e "não cria no brain"); mantém `projeto_fato`/`projeto_gasto`/`projeto_pessoa`/`projeto_anexar`/`projeto_atualizar`. Rodar → FAIL.
- [ ] **Step 2: Editar o SOUL** conforme Produces; trocar `projeto_criar` por fluxo Linear+`projeto_ligar`; tirar menção a `depois_de`/`marco`.
- [ ] **Step 3: Rodar** `.venv/bin/pytest tests/mcp/test_hermes.py -q` → PASS.
- [ ] **Step 4: Commit** `feat(hermes): SOUL com a fronteira Linear/brain (ADR-038)`.

### Task 4: Painel Dia › Projetos vira a pasta

**Files:**
- Modify: `painel/src/telas/Projetos.tsx` (tirar progresso na lista e `feitas/total`, detalhe de etapas/próximas/bloqueadas/atrasadas; manter orçamento×gasto, fatos, anexos, pessoas, concluir/cancelar; botão "Abrir no Linear" quando `linear_url`), `gabi/rotas/projetos.py` se a rota de criar do painel ficar sem sentido (manter, não é pedido remover), `tests/rotas/` do painel/projetos se houver asserção sobre `progresso`
- Test: teste de rota existente de projetos (garantir `linear_url`/`linear_id` na resposta) + `cd painel && npm run build` sem erro de tipo

**Interfaces:**
- Consumes: `linear_id`, `linear_url` em listar/ver (Task 1).

- [ ] **Step 1: Teste de rota** (no arquivo de rotas de projetos existente) que cria projeto, liga com `projetos.ligar` e confere `GET /api/v1/projetos/{id}` com `linear_url`. Rodar → FAIL se faltar chave.
- [ ] **Step 2: Editar `Projetos.tsx`** conforme Files; link `target="_blank" rel="noopener noreferrer"`; projeto sem `linear_url` não mostra o botão.
- [ ] **Step 3: Rodar** `cd painel && npm run build` (sem erro) e `.venv/bin/pytest tests/rotas -q` → PASS.
- [ ] **Step 4: Commit** `feat(painel): Projetos vira a pasta, com link para o Linear`.

### Task 5: Docs, runbook `#linear`, ADR e STATUS/BACKLOG

**Files:**
- Modify: `docs/adr/038-projetos-no-linear.md` (estado: implementado na branch, não instalado), `docs/runbook.md` (nova seção `{#linear}` com a instalação e o desfazer da spec; corrigir a contagem 75→75 no include e mencionar `projeto_criar` fora), `docs/STATUS.md`, `docs/BACKLOG.md` (item LN1: instalação + aceite + decisão do espelho após um mês), `docs/HANDOFF.md`, `docs/adr/034-projetos.md` (nota "substituído em parte pelo ADR-038")

- [ ] **Step 1: Escrever a seção `#linear`** com os passos da spec: backup `gabi.db.antes-linear-<data>`; `cd ~/gabi-brain/painel && npm run build`; `sudo ~/instalar-brain.sh`; backup `~/.hermes/config.yaml.bak-antes-linear`; incluir `mcp_servers.linear` (MCP oficial, chave que o Ricardo coloca em `~/.hermes/.env`; se exigir OAuth, fluxo em segundo plano e ele digita o código) com `include` fechado (listar/ver/criar/mudar projeto e etapa, comentar; sem apagar; nomes conferidos nas ferramentas que o servidor oferece); novo include do brain (`docs/fontes/hermes.md`); SOUL; restart `hermes-gateway`; `/new`; aceite real e desfazer como na spec.
- [ ] **Step 2: Atualizar** os demais documentos.
- [ ] **Step 3: Suíte e lint completos:** `.venv/bin/pytest -q` (ler o resumo) e o lint do projeto (`ruff check` se configurado em `pyproject.toml`) → verdes.
- [ ] **Step 4: Commit** `docs: ADR-038 implementado, runbook #linear, STATUS e BACKLOG`.

---

## Self-review

- Cobertura da spec: migração 0089 (T1), `projeto_ligar` + include + params (T2), `projeto_listar/ver` com link (T1/T2), painel (T4), `projeto_parado` (T1), SOUL (T3), testes listados (T1–T4), aceite/instalação/desfazer (T5). `mcp_servers.linear` do Hermes é só instalação (T5), por exigir a chave dele.
- Consistência de nomes: `ligar`, `projeto_ligar`, `linear_id`, `linear_url`, `FORA_DO_HERMES`, `ferramentas_do_hermes` iguais em todas as tarefas.
- Proporção: 5 tarefas; corpo de código só onde a assinatura e os testes não decidem.
