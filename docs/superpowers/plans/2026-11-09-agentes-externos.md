# Agentes externos (ADR-036) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emitir, ajustar, rotacionar e revogar chaves do MCP pelo painel (Gabi › Agentes) e copiar receitas de conexão para os agentes do Ricardo, sem terminal da VPS.

**Architecture:** Camada fina sobre `gabi/mcp/tokens.py` (nenhuma regra de segurança nova): um módulo de regras `gabi/agentes.py` (último uso, contagens, `decisao`, rotacionar), um router `gabi/rotas/agentes.py` (`/api/v1/agentes`, nível `boss`) e uma tela `painel/src/telas/Gabi/Agentes.tsx` com receitas. Sem migração: último uso e contagem saem de `chamada_mcp`.

**Tech Stack:** Python/FastAPI/SQLite (pytest), React/TypeScript (vitest), painel buildado em `gabi/painel/`.

**Spec:** `docs/superpowers/specs/2026-11-09-agentes-externos-design.md`

## Global Constraints

- Toda chave nova nasce com `ESCOPOS_HERMES` (`gabi/mcp/servidor.py:65`), sem `sensivel`; o dono desmarca o que não quiser. Sem perfis prontos.
- Só agentes dele, dentro da Tailscale; OpenAI API e agentes em nuvem ficam fora e a tela diz isso.
- Segredo aparece uma única vez (resposta do POST/rotacionar); `GET` nunca devolve segredo nem hash; `decisao` nunca contém o segredo.
- Validação de nome e escopos = a de `gabi.mcp.tokens` (`ESCOPOS`); erros: `ValueError` → 400 `requisicao_invalida`, `LookupError` → 404 `nao_encontrado`.
- Chamadas recentes: ferramenta, status, quando; nunca argumentos nem resultados.
- URL do MCP: parâmetro `mcp.url`, padrão `https://gabi-brain.tail985643.ts.net:8443/mcp`.
- Fora do escopo: validade, limite de chamadas, lista de ferramentas por chave, OAuth, URL pública, chaves para terceiros, ferramentas MCP novas (contagem de 71 não muda).
- Nada instala/merge sem ok explícito do Ricardo; antes de instalar: `cd painel && npm run build` e conferir `gabi/painel/`.
- Branch própria `feat/agentes-externos` (worktree `~/gabi-brain-agentes`), a partir da main.

## Review Focus

- Rotacionar a chave do Hermes: a antiga deixa de autenticar na hora e a tela exige confirmação reforçada (teste: antiga → `nao_autenticado`, nova → ok).
- Rotacionar falha no meio (escopos inválidos herdados): nada pode ficar revogado sem nova emitida (teste: transação única, antiga continua ativa se emitir falha).
- Editar escopos de chave revogada: 404, não reativa nada.
- Nome só com espaços e escopos vazios na criação: 400, sem linha em `token_agente`.
- Chave nova nunca usada: "último uso" nulo e 0 chamadas em 7 dias, a tela mostra "nunca usada" (sem quebrar).
- Chamadas de token revogado continuam visíveis no histórico da chave.

---

### Task 1: Regras em `gabi/agentes.py`

**Files:**
- Create: `gabi/agentes.py`
- Test: `tests/test_agentes.py`

**Interfaces:**
- Consumes: `gabi.mcp.tokens` (`emitir`, `revogar`, `definir_escopos`, `listar`, `_hash` não); `gabi.mcp.servidor.ESCOPOS_HERMES`; tabelas `token_agente`, `chamada_mcp`, `decisao(quando, quem, o_que, origem)`.
- Produces (todas recebem `con: sqlite3.Connection`; `agora: datetime` aware; `quem: str`):
  - `listar_agentes(con, agora) -> list[dict]` — itens `{id, nome, escopos, criado_em, revogado_em, ativo, ultimo_uso: str|None, chamadas_7d: int}`, ordem por id.
  - `criar(con, agora, quem, nome, escopos: list[str]|None) -> dict` — `escopos=None` usa `ESCOPOS_HERMES`; retorna `{"id", "nome", "escopos", "chave"}`.
  - `trocar_escopos(con, agora, quem, token_id, escopos) -> dict` — retorna item atualizado (sem `chave`).
  - `revogar_agente(con, agora, quem, token_id) -> dict`.
  - `rotacionar(con, agora, quem, token_id) -> dict` — mesmo formato de `criar`, nome igual ao antigo; antiga revogada na mesma transação.
  - `chamadas(con, token_id, limite=50) -> list[dict]` — `{quando, ferramenta, status}` mais recentes primeiro; `LookupError` se o token não existe.
  - `conexao(con) -> dict` — `{"url": <mcp.url ou padrão>, "escopos_padrao": list(ESCOPOS_HERMES), "escopos_validos": sorted(ESCOPOS)}`.

- [ ] **Step 1: Write the failing tests** em `tests/test_agentes.py` (banco migrado como em `tests/mcp/test_servidor.py`): `test_criar_devolve_chave_uma_vez_e_usa_escopos_do_hermes`, `test_listar_nunca_devolve_segredo_nem_hash` (nenhum valor começa com `gb_` e a chave `hash` não existe), `test_criar_rejeita_nome_vazio_e_escopo_invalido` (`ValueError`, 0 linhas), `test_trocar_escopos_nao_muda_segredo` (a chave antiga ainda valida via `tokens.validar`), `test_trocar_escopos_de_revogada_levanta_lookuperror`, `test_revogar_faz_validar_devolver_none`, `test_rotacionar_revoga_antiga_e_emite_nova_com_mesmos_escopos`, `test_rotacionar_atomico_se_emitir_falha` (escopo gravado inválido via UPDATE direto → `ValueError`, antiga segue ativa), `test_ultimo_uso_e_contagem_7d` (3 linhas em `chamada_mcp`: duas dentro de 7 dias, uma de 10 dias atrás → `chamadas_7d == 2`, `ultimo_uso` = a mais recente), `test_chave_nunca_usada_tem_ultimo_uso_none_e_zero`, `test_cada_operacao_grava_decisao_sem_segredo` (4 linhas em `decisao` com `origem='agentes'`, nenhuma contém `gb_`), `test_chamadas_de_revogada_continuam_visiveis`, `test_conexao_usa_parametro_ou_padrao` (parametro `mcp.url` gravado como JSON `"\"https://x/mcp\""`).
- [ ] **Step 2: Run** `pytest tests/test_agentes.py -v` → FAIL (`ModuleNotFoundError: gabi.agentes`).
- [ ] **Step 3: Implement `gabi/agentes.py`** com as assinaturas acima. `rotacionar` e `criar` usam `with con:` para atomicidade (emitir primeiro; só então revogar). `decisao.o_que` no formato `agente <id> "<nome>": emitida|escopos=<lista>|revogada|rotacionada (nova <id2>)`; `quem` e `agora.astimezone(UTC).isoformat()` como em `gabi/atividades.py:76`. `mcp.url` lido com o mesmo padrão de `gabi.avisos._parametro` (JSON em `parametro.valor`); importe-o em vez de duplicar.
- [ ] **Step 4: Run** `pytest tests/test_agentes.py -v` → PASS.
- [ ] **Step 5: Commit** `git add gabi/agentes.py tests/test_agentes.py && git commit -m "feat(agentes): regras de chaves do MCP (ADR-036)"`.

### Task 2: API `/api/v1/agentes`

**Files:**
- Create: `gabi/rotas/agentes.py`
- Modify: `gabi/api.py:167-170` (incluir o router, ao lado de `rotas_atividades`)
- Test: `tests/rotas/test_agentes_api.py`

**Interfaces:**
- Consumes: Task 1; padrão de `gabi/rotas/atividades.py` (`_rodar`, `_corpo`, `_json`, `erro`, `exigir("boss")`, `envelope`).
- Produces: `router = APIRouter(prefix="/api/v1/agentes", dependencies=[Depends(exigir("boss"))])` com `GET ""` → `{itens}`; `POST ""` (201, corpo `{nome, escopos?}`, resposta inclui `chave`); `PATCH "/{id}/escopos"` (`{escopos}`); `POST "/{id}/revogar"`; `POST "/{id}/rotacionar"` (resposta inclui `chave`); `GET "/{id}/chamadas"` → `{itens}`; `GET "/conexao"` (declarar **antes** de `/{id}/...`). `quem` = login da identidade. Campos desconhecidos no corpo → 400.

- [ ] **Step 1: Write the failing tests** (fixtures `cli`, `req`, `BOSS`, `VIP` de `tests/rotas/test_cadastros_api.py`): `test_vip_nao_acessa` (403 em GET e POST), `test_criar_devolve_chave_e_listar_nao`, `test_criar_sem_escopos_usa_padrao_do_hermes_sem_sensivel`, `test_nome_vazio_400`, `test_escopo_invalido_400`, `test_campo_desconhecido_400`, `test_patch_escopos_e_404_em_revogada`, `test_revogar_e_rotacionar` (a chave antiga passa a dar 401 `nao_autenticado` em `POST /mcp`, a nova responde 200 em `tools/list`), `test_id_inexistente_404`, `test_chamadas_traz_ferramenta_status_quando_sem_argumentos`, `test_conexao_devolve_url_padrao`, `test_decisao_gravada_com_login_do_painel`.
- [ ] **Step 2: Run** `pytest tests/rotas/test_agentes_api.py -v` → FAIL (404 nas rotas).
- [ ] **Step 3: Implement** `gabi/rotas/agentes.py` e registrar em `gabi/api.py`. Resposta de criar/rotacionar não passa pelo cache: sem tratamento extra, mas confirmar que o envelope não registra o corpo em log.
- [ ] **Step 4: Run** `pytest tests/rotas/test_agentes_api.py tests/mcp -q` → tudo PASS (garante que o MCP segue igual).
- [ ] **Step 5: Commit** `git commit -m "feat(agentes): API /api/v1/agentes"` (add dos dois arquivos de rota, `gabi/api.py` e o teste).

### Task 3: Tela Gabi › Agentes (lista, nova chave, ações)

**Files:**
- Create: `painel/src/telas/Gabi/Agentes.tsx`
- Modify: `painel/src/navegacao.ts` (na área `gabi`: aba `["agentes", "Agentes", "Quais agentes meus acessam a Gabi?"]`), `painel/src/App.tsx` (`TELAS.agentes = Agentes`)
- Test: `painel/tests/agentes.test.tsx`

**Interfaces:**
- Consumes: Task 2; `useApi`, `useAcao`, `api.get/post/patch`, `Painel`, `Bloco`, `Aviso` (padrão de `painel/src/telas/Atividades.tsx`); fixtures `apiFalsa`/`amostra` de `painel/tests/apiFalsa.ts` (acrescentar a amostra `agentes` se o gerador for necessário; senão objeto escrito no teste, como em `qualidade.test.tsx`).
- Produces: `export function Agentes()`; estado local `chaveRecente: {id, valor} | null` (usado pela Task 4 para preencher receitas).

- [ ] **Step 1: Write the failing tests** em `painel/tests/agentes.test.tsx`: `lista chaves com último uso, chamadas em 7 dias e revogadas esmaecidas` (linha sem uso mostra "nunca usada"), `nova chave vem com os escopos do Hermes marcados e sem sensivel` (checkboxes: `sensivel` desmarcado), `nome vazio bloqueia o envio`, `ao emitir mostra a chave uma vez com botão Copiar e some ao fechar` (depois de fechar, `queryByText(/gb_/)` é nulo), `revogar pede confirmação`, `rotacionar e revogar a chave do Hermes pedem confirmação reforçada` (texto cita Telegram e WhatsApp), `editar escopos chama PATCH sem mostrar chave`, `ver chamadas lista ferramenta, status e quando`.
- [ ] **Step 2: Run** `cd painel && npx vitest run tests/agentes.test.tsx` → FAIL.
- [ ] **Step 3: Implement** `Agentes.tsx` e registrar aba/tela. A linha do Hermes é identificada pelo nome `hermes` (case-insensitive) — é só para a confirmação reforçada. Copiar usa `navigator.clipboard.writeText` com `try/catch` (se falhar, o texto continua selecionável).
- [ ] **Step 4: Run** `npx vitest run` (suíte toda do painel) → PASS; `npx tsc --noEmit` → sem erros.
- [ ] **Step 5: Commit** `git commit -m "feat(agentes): tela Gabi › Agentes no painel"`.

### Task 4: Receitas de conexão

**Files:**
- Create: `painel/src/telas/Gabi/receitas.ts` (função pura), `painel/src/telas/Gabi/ReceitasAgentes.tsx`
- Modify: `painel/src/telas/Gabi/Agentes.tsx` (renderizar `ReceitasAgentes` abaixo da lista)
- Test: `painel/tests/receitas.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/agentes/conexao` (`url`); `chaveRecente` da Task 3.
- Produces: `receitas(url: string, chave: string | null): {id: string; titulo: string; texto: string; nota?: string}[]` — usa `chave ?? "<SUA_CHAVE>"`; clientes: Claude Code, Cursor, Codex CLI, Claude Desktop/VS Code/Gemini CLI (via `mcp-remote` quando não houver config nativa) e o bloco "Não suportado" (OpenAI API e agentes em nuvem: precisam de URL pública). Todas terminam com o teste de 1 linha: pedir ao agente para chamar `ferramentas_ver`.

- [ ] **Step 1: Write the failing tests:** `sem chave recente usa <SUA_CHAVE> e nunca um segredo`, `com chave recente preenche só a receita e a variável de ambiente`, `Claude Code usa claude mcp add --transport http com header Authorization Bearer`, `Cursor traz url e headers`, `Codex usa bearer_token_env_var`, `toda receita inclui o teste ferramentas_ver`, `aviso de não suportado cita OpenAI API e nuvem`, `a URL vem do /conexao`.
- [ ] **Step 2: Run** `npx vitest run tests/receitas.test.tsx` → FAIL.
- [ ] **Step 3: Conferir a sintaxe atual de cada cliente na documentação oficial** (WebFetch/WebSearch; muda com frequência) **antes** de fixar os textos; registrar clientes e data da conferência (`docs/runbook.md`, Task 5). Implementar `receitas()` e o componente (cartões com botão Copiar; receitas recomendam variável de ambiente `GABI_BRAIN_TOKEN`, não gravar a chave em arquivo).
- [ ] **Step 4: Run** `npx vitest run` e `npx tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(agentes): receitas de conexão por cliente"`.

### Task 5: Documentação, contrato e fechamento

**Files:**
- Create: `docs/adr/036-agentes-externos.md`
- Modify: `docs/adr/README.md` (linha 036), `docs/runbook.md` (seção "Agentes externos": emitir pelo painel, conectar, revogar, data da conferência das receitas, passos de instalação), `docs/api.md` e `docs/openapi.json` (regenerar com o gerador existente — ver a referência a `openapi.json` no `docs/runbook.md`/`Makefile`), `docs/BACKLOG.md` (linha do ADR-036 e nota de que `feat/projetos-melhorias` passa a ADR-037), `docs/STATUS.md`
- Test: suíte completa

- [ ] **Step 1:** Escrever o ADR-036 (contexto, decisões do Ricardo de 09/11, riscos aceitos: escopos de escrita por padrão) e as seções de docs.
- [ ] **Step 2:** Regenerar `docs/openapi.json` e conferir que o teste de contrato/`test_api` que compara a spec passa.
- [ ] **Step 3: Run** `pytest -q` e `cd painel && npx vitest run && npm run build` → tudo PASS; conferir que `gabi/painel/` foi atualizado.
- [ ] **Step 4: Commit** `git commit -m "docs(agentes): ADR-036, runbook, api e backlog"`.
- [ ] **Step 5 (só com ok do Ricardo):** `sudo ~/instalar-brain.sh`; aceite: pelo painel emitir chave "teste", colar a receita do Claude Code em outra máquina da tailnet, o agente chama `ferramentas_ver` e a chamada aparece em Agentes; revogar e a chamada seguinte falha com `nao_autenticado`. Merge e instalação não rodam sem pedido explícito.
