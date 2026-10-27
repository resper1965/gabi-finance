# Atividades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Ricardo deixa um recado ao Hermes (Telegram ou WhatsApp) e ele cria uma atividade (to-do pessoal) que aparece no painel e gera avisos no Telegram.

**Architecture:** Um módulo de regras novo, `gabi/atividades.py`, sobre a tabela nova `atividade` (migração 0086). A API (`gabi/rotas/atividades.py`), o MCP (`gabi/mcp/ferramentas_atividades.py`) e o painel só chamam esse módulo. Os avisos reaproveitam o produtor (`gabi/avisos.py`, timer de 15 min) e a entrega do Telegram: o módulo devolve o que está devido e `gerar_avisos` grava em `aviso`.

**Tech Stack:** Python 3 + FastAPI + SQLite (migrações SQL), pytest; painel React + TypeScript + vitest; servidor MCP (`gabi/mcp`).

**Spec:** `docs/superpowers/specs/2026-10-27-atividades-design.md` (modelo de despesas como referência de estilo: `gabi/dinheiro/despesas.py`, `gabi/rotas/despesas.py`, `gabi/mcp/ferramentas_despesas.py`).

## Global Constraints
- Datas/horas de entrada e saída são locais de Brasília: `AAAA-MM-DD` (dia todo) ou `AAAA-MM-DDTHH:MM` (com hora). No banco, `vence_em` é ISO em UTC; `tem_hora=0` guarda 00:00 BRT do dia. "Hoje" = `agora.astimezone(BRT).date()` (`from gabi.hoje import BRT`).
- `origem` = `'hermes'` (MCP) ou `'painel'`; `quem` = `'hermes'` no MCP e o login no painel.
- Toda escrita grava uma linha em `decisao` (`quando`, `quem`, `o_que`, `origem`) na mesma transação.
- Texto da atividade: até 500 caracteres, nunca mascarado, nunca em log.
- Estados: `aberta` → `feita` ou `cancelada`. Não existe reabrir (para voltar, criar de novo). Repetir a mesma transição é idempotente; a transição para o outro estado final é `ValueError`.
- Avisos: um por (tipo, chave) por dia de Brasília (regra do `_novo`); 07:00 BRT é o início da manhã; o Telegram só envia avisos dos últimos 2 dias (`JANELA_ENTREGA`).
- O Hermes cria sem pedir confirmação (reversível); nunca a partir de texto de e-mail, Teams ou documento.
- Textos do painel, do SOUL e dos avisos em português do Brasil. Nada de gráficos no painel.
- Nada é mergeado nem instalado sem o ok explícito do Ricardo.

## Review Focus
1. **Virada de dia em Brasília:** atividade de `2026-10-28T23:50` BRT é "hoje" em 28/10 mesmo quando o UTC já é 29/10. Teste na Task 2.
2. **Adiar depois do aviso enviado:** o aviso antigo fecha sem reenviar e o novo horário gera aviso novo. Teste na Task 2.
3. **Concluir antes do horário:** o aviso nunca sai (`triar` → resolvido). Teste na Task 2.
4. **Hermes repete a chamada:** `criar` igual a uma aberta devolve `ja_existia`, sem duplicar. Teste na Task 1 e na Task 4.
5. **Resumo grande ou vazio:** vazio não gera aviso; mais de 15 linhas vira "e mais N". Teste na Task 2.
6. **Texto estranho:** só espaços, 501 caracteres, aspas e emoji. Teste na Task 1.

---

### Task 1: Migração 0086 e regras (`gabi/atividades.py`)

**Files:**
- Create: `migrations/0086_atividades.sql`, `gabi/atividades.py`
- Test: `tests/test_atividades.py`

**Interfaces:**
- Produces (todas em `gabi.atividades`; `LookupError` = id inexistente, `ValueError` = dado ou transição inválida):
  - `criar(con, agora: dt.datetime, quem: str, origem: str, texto: str, vence_em: str | None = None) -> dict`
  - `listar(con, agora: dt.datetime, status: str = "aberta") -> list[dict]`
  - `concluir(con, agora, quem, origem, id_: int) -> dict`, `cancelar(con, agora, quem, origem, id_: int) -> dict`
  - `adiar(con, agora, quem, origem, id_: int, vence_em: str) -> dict`
  - `abertas_por_texto(con, trecho: str) -> list[dict]` (para o MCP resolver "ligar pro contador")
  - Item: `{"id": int, "texto": str, "vence_em": str | None, "tem_hora": bool, "status": str, "origem": str, "criada_em": str, "concluida_em": str | None, "prazo": "vencida"|"hoje"|"proxima"|"sem_data"}`; `criar` acrescenta `"ja_existia": bool`. `vence_em` sai no mesmo formato local de entrada.

- [ ] **Step 1: Write the failing tests** em `tests/test_atividades.py` (fixture `con` como em `tests/test_avisos.py`; `AGORA = 2026-10-27 15:00 UTC` = 12:00 BRT):
  - `test_criar_com_hora_guarda_utc_e_devolve_local`: `criar(..., "ligar pro contador", "2026-10-30T10:00")` → `vence_em == "2026-10-30T10:00"`, `tem_hora is True`, linha no banco com `vence_em == "2026-10-30T13:00:00+00:00"`, uma linha em `decisao` com `origem='hermes'`.
  - `test_criar_so_data_vale_o_dia_todo`: `"2026-10-30"` → `tem_hora False`, `prazo == "proxima"`; sem data → `prazo == "sem_data"`.
  - `test_criar_recusa_passado`: data de ontem e hora de 1 min atrás hoje → `ValueError`; hoje sem hora → aceito (`prazo == "hoje"`).
  - `test_criar_recusa_texto_vazio_e_longo`: `"   "` e `"x"*501` → `ValueError`; `"x"*500`, aspas e emoji aceitos e devolvidos idênticos.
  - `test_criar_igual_a_aberta_nao_duplica`: segunda chamada igual → mesmo `id`, `ja_existia True`, uma linha só; texto igual com outro vencimento cria nova; igual a uma `feita` cria nova.
  - `test_listar_ordem`: vencida (ontem às 09:00 inserida direto no banco), hoje, próxima, sem data → nessa ordem; `status="feita"` lista só as feitas.
  - `test_concluir_e_cancelar_idempotentes_e_exclusivos`: concluir duas vezes ok; cancelar uma feita → `ValueError`; id 999 → `LookupError`.
  - `test_adiar_so_aberta_e_valida_futuro`: adiar muda `vence_em`/`tem_hora`; adiar feita → `ValueError`; adiar para o passado → `ValueError`.
  - `test_abertas_por_texto_ignora_acento_e_caixa`.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_atividades.py -q` → FAIL (módulo não existe).

- [ ] **Step 3: Implement** `migrations/0086_atividades.sql`: `atividade(id integer primary key, texto text not null, vence_em text, tem_hora integer not null default 0, status text not null default 'aberta' check (status in ('aberta','feita','cancelada')), origem text not null, criada_em text not null, concluida_em text)` mais `create index atividade_status_vence on atividade(status, vence_em)`; cabeçalho com spec, como a 0084, e a linha de desfazer (`drop table atividade; delete from schema_versao where nome='0086_atividades.sql';`). Implemente `gabi/atividades.py` com o docstring no estilo de `despesas.py` (consome/produz). Uma função privada `_parse(vence_em, agora) -> (utc_iso | None, tem_hora)` e `_item(row, agora)` (calcula `prazo`) concentram a conversão BRT↔UTC; comparação de "igual" usa texto normalizado (sem acento, caixa baixa, espaços colapsados) e o mesmo `vence_em` UTC.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_atividades.py -q` → PASS; `.venv/bin/pytest -q -x -k "esquema or db"` → PASS (a suíte de esquema conhece a migração nova).

- [ ] **Step 5: Commit** `git add migrations/0086_atividades.sql gabi/atividades.py tests/test_atividades.py docs/superpowers && git commit -m "feat(atividades): tabela e regras"` (com o `Co-Authored-By` pedido no ambiente).

---

### Task 2: Avisos (produtor, revalidação, texto)

**Files:**
- Modify: `gabi/atividades.py` (acrescenta `avisos_devidos`), `gabi/avisos.py` (chamada em `gerar_avisos`, `TIPOS_REVALIDADOS`, ramo em `revalidar`), `gabi/rotas/avisos.py` (`descrever`)
- Test: `tests/test_atividades_avisos.py`

**Interfaces:**
- Consumes: Task 1 (`atividade` e `_item`).
- Produces: `atividades.avisos_devidos(con, agora: dt.datetime) -> list[tuple[str, str, dict]]` = `(tipo, chave, payload)` para `novo(tipo, chave, payload)` de `gerar_avisos`. Tipos e payloads:
  - `atividade_hora`: chave `f"{id}|{vence_em_utc}"`, payload `{"id", "texto", "vence_em"}` (local); devido se `tem_hora`, aberta, `vence_em <= agora` e dentro dos últimos 2 dias.
  - `atividade_hoje`: chave `str(id)`, payload igual; devido se aberta, vencimento no dia de Brasília de hoje e `agora >= 07:00 BRT`.
  - `atividade_resumo`: chave `hoje.isoformat()`, payload `{"vencidas": [...], "hoje": [...], "sem_data": [...], "total": n}` (cada item `{"id","texto","vence_em"}`; no máximo 15 itens somados, vencidas primeiro; `total` é a contagem real); devido se `agora >= 07:00 BRT` e `total > 0`.
- `avisos.TIPOS_REVALIDADOS` ganha os três tipos; `revalidar` ganha: `atividade_hora`/`atividade_hoje` → `VALE` só se a atividade segue `aberta` e `vence_em` igual ao do payload, senão `RESOLVIDO`; `atividade_resumo` → relê as abertas e devolve `(VALE, payload_atual)` ou `RESOLVIDO` se não sobrou nada.
- `rotas.avisos.descrever(tipo, p)` ganha os três tipos em pt-BR (ex.: título `"Atividade agora: ligar pro contador"` / texto `"marcada para 10:00"`; `"Atividade para hoje: …"`; `"Atividades: 2 vencidas, 1 para hoje, 3 sem data"` com as linhas no texto e `"e mais N"` quando passa de 15).

- [ ] **Step 1: Write the failing tests** (fixture `con` e `AGORA` como em `tests/test_avisos.py`, relógio injetado; use `gerar_avisos`, `triar` e `descrever`):
  - `test_aviso_na_hora_so_depois_do_horario`: às 12:00 BRT não sai atividade das 13:00; às 13:05 sai um `atividade_hora`; segunda rodada no mesmo dia não duplica.
  - `test_hoje_e_resumo_so_depois_das_7h_brt`: às 06:59 BRT nada; às 07:01 saem `atividade_hoje` (das de hoje) e um `atividade_resumo`.
  - `test_resumo_vazio_nao_sai_e_grande_vira_e_mais_n`: sem atividade aberta → nenhum aviso; 20 sem data → payload com 15 itens e `total == 20`, texto de `descrever` termina com `e mais 5`.
  - `test_resumo_separa_vencidas_hoje_e_sem_data`.
  - `test_virada_de_dia_brt`: atividade `2026-10-28T23:50` BRT com `agora` = 29/10 02:30 UTC (23:30 BRT de 28/10) conta como "hoje" no resumo, e não como vencida.
  - `test_concluir_antes_do_horario_nunca_envia`: cria, conclui, `triar` do aviso (ou `gerar_avisos` + `triar`) → `"resolvido"` e `telegram_em == entregue_em`.
  - `test_adiar_fecha_o_aviso_antigo_e_gera_outro`: aviso `atividade_hora` já gerado; `adiar` para amanhã 09:00; próxima `gerar_avisos` fecha o velho sem enviar; no horário novo sai outro (chave nova).
  - `test_descrever_pt_br`: três tipos, sem `json.dumps` cru no texto.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_atividades_avisos.py -q` → FAIL.

- [ ] **Step 3: Implement** `avisos_devidos` em `gabi/atividades.py` (só leitura, relógio por parâmetro). Em `gerar_avisos`, antes do `return criados`: `for tipo, chave, p in atividades.avisos_devidos(con, agora): novo(tipo, chave, p)` (import dentro da função se houver ciclo). Ramos de `revalidar` e `descrever` conforme Interfaces.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_atividades_avisos.py tests/test_avisos.py tests/test_avisos_antecipados.py -q` → PASS (os avisos antigos continuam verdes).

- [ ] **Step 5: Commit** `feat(atividades): avisos na hora, no dia e resumo da manhã`.

---

### Task 3: API (`/api/v1/atividades`)

**Files:**
- Create: `gabi/rotas/atividades.py`
- Modify: `gabi/api.py` (include do router, junto de `rotas_despesas`, ~linha 164), `docs/api.md`
- Test: `tests/rotas/test_atividades.py`

**Interfaces:**
- Consumes: Task 1.
- Produces (padrão de `gabi/rotas/despesas.py`: `_rodar`, `exigir("boss")`, `envelope`; `LookupError`→404 `nao_encontrado`, `ValueError`→400 `requisicao_invalida`):
  - `GET /api/v1/atividades?status=aberta|feita|cancelada` → `{"itens": [item]}`
  - `POST /api/v1/atividades` `{texto, vence_em?}` → 201 + item
  - `POST /api/v1/atividades/{id}/concluir` e `/cancelar` → item
  - `PATCH /api/v1/atividades/{id}` `{vence_em}` → item (adiar)

- [ ] **Step 1: Write the failing tests** (como `tests/rotas/test_despesas*.py`): criar → 201 e aparece no GET; `status` inválido → 400; concluir some do `aberta` e aparece em `feita`; id inexistente → 404; PATCH para o passado → 400; corpo com campo desconhecido → 400; sem login de boss → o mesmo 401/403 que as outras rotas; cada escrita grava `decisao` com `origem='painel'`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/rotas/test_atividades.py -q` → FAIL.
- [ ] **Step 3: Implement** o router e registre-o em `gabi/api.py`; documente as quatro rotas em `docs/api.md` (há teste de documentação: `tests/test_docs_api.py` diz o formato).
- [ ] **Step 4: Run** `.venv/bin/pytest tests/rotas/test_atividades.py tests/test_docs_api.py tests/test_matriz_acesso.py -q` → PASS (a matriz de acesso exige a rota nova na lista de `boss`).
- [ ] **Step 5: Commit** `feat(atividades): API`.

---

### Task 4: Ferramentas do Hermes (MCP) e escopo `atividades`

**Files:**
- Create: `gabi/mcp/ferramentas_atividades.py`
- Modify: `gabi/mcp/tokens.py` (`ESCOPOS` ganha `"atividades"`), `gabi/mcp/servidor.py` (import, `ESCOPOS_FERRAMENTAS`, `FONTES_DA_FERRAMENTA` com `()`, `registrar`, texto de `instructions`), `docs/fontes/hermes.md` (lista oficial do include: 55 → 60)
- Test: `tests/mcp/test_atividades_mcp.py`; atualizar `tests/mcp/test_servidor.py`, `tests/mcp/test_hermes.py` e o teste de tokens que enumera `ESCOPOS`

**Interfaces:**
- Consumes: Task 1. Padrão: `gabi/mcp/ferramentas_despesas.py` (`NOMES`, `ESCOPOS`, `QUEM = ORIGEM = "hermes"`, `ErroFerramenta`, `registrar(srv, executar)`).
- Produces: `NOMES = ("atividade_criar", "atividade_listar", "atividade_concluir", "atividade_adiar", "atividade_cancelar")`, `ESCOPOS = {n: "atividades" for n in NOMES}`. Assinaturas (primeiro `con, agora`):
  - `atividade_criar(con, agora, texto, vence="") -> dict` (item + `desfazer: 'atividade_cancelar(<id>)'`; `vence` local `AAAA-MM-DD` ou `AAAA-MM-DDTHH:MM`)
  - `atividade_listar(con, agora, status="aberta") -> {"itens": [...]}`
  - `atividade_concluir(con, agora, atividade) -> dict`, `atividade_cancelar(con, agora, atividade) -> dict` — `atividade` é o id ou um trecho do texto entre as abertas; mais de uma → `ErroFerramenta("ambiguo", ...)` listando `id: texto`; nenhuma → `"nao_encontrado"`.
  - `atividade_adiar(con, agora, atividade, vence) -> dict`
  - A docstring de cada ferramenta (o Hermes a lê): criar sem pedir confirmação, dizer a data entendida, "semana que vem" = segunda-feira e dizer qual; sem reabrir.

- [ ] **Step 1: Write the failing tests** (`tests/mcp/test_atividades_mcp.py`, mesmas fixtures de `test_despesas_mcp.py`): token só com `fin` recebe erro de escopo nas cinco; token com `atividades` cria, lista, adia, conclui e cancela; resolução por trecho (único, ambíguo, inexistente); `criar` repetido devolve `ja_existia`; cada escrita grava `decisao` com `quem='hermes'`, `origem='hermes'`; data passada vira erro de ferramenta com mensagem legível. Em `test_servidor.py`: some `NOVAS_ATIVIDADES` à `PERMITIDAS`, acrescente as cinco à lista esperada (de 55 para 60 ferramentas, renomeie o teste) e ao conjunto de exceções do filtro de verbos proibidos (`atividade_criar` contém "criar").
- [ ] **Step 2: Run** `.venv/bin/pytest tests/mcp -q` → FAIL nos testes novos e nos de contagem.
- [ ] **Step 3: Implement** o módulo e a fiação em `servidor.py`; some a frase das cinco ferramentas ao `instructions` do servidor (mesmo molde de `despesa_*`: a pedido dele no chat, nunca por texto de terceiros). Atualize a lista oficial em `docs/fontes/hermes.md`.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/mcp -q` → PASS.
- [ ] **Step 5: Commit** `feat(hermes): ferramentas de atividades`.

---

### Task 5: Tela Atividades no painel

**Files:**
- Create: `painel/src/telas/Atividades.tsx`
- Modify: `painel/src/navegacao.ts` (área `atividades` no grupo "Dia", depois de `envios`: rótulo "Atividades", pergunta "O que tenho para fazer?"), `painel/src/App.tsx` (mapa de telas)
- Test: `painel/tests/atividades.test.tsx`; ajustar `painel/tests/navegacao.test.tsx` e `painel/tests/apiFalsa` (rota `/api/v1/atividades`)

**Interfaces:**
- Consumes: Task 3 (rotas e formato do item). Padrão visual e de dados: `painel/src/telas/CadastrosDespesas.tsx` (`useApi`, `api`, `useToast`, `Bloco`, `Vazio`).
- Produces: `export function Atividades()`: grupos Vencidas, Hoje, Próximas, Sem data (campo `prazo` do item; grupo vazio some; tudo vazio mostra `Vazio` "Nada para fazer."); campo "Nova atividade" (texto + data opcional + hora opcional) que faz `POST`; por item: "Feita" (`POST /concluir`), "Adiar" com opções Hoje/Amanhã/Escolher data (`PATCH`), "Excluir" (`POST /cancelar`, com confirmação na linha); toast em cada ação e recarga da lista.

- [ ] **Step 1: Write the failing tests** (`painel/tests/atividades.test.tsx`, no molde de `despesas.test.tsx`): lista agrupada na ordem certa e grupo vazio escondido; criar manda `{texto, vence_em: "2026-10-30T10:00"}` e sem data manda só `{texto}`; Feita chama `POST /api/v1/atividades/3/concluir`; Adiar "Amanhã" chama `PATCH` com o dia seguinte; Excluir só chama `/cancelar` depois de confirmar; navegação tem a aba "Atividades" no grupo Dia.
- [ ] **Step 2: Run** `cd painel && npx vitest run tests/atividades.test.tsx tests/navegacao.test.tsx` → FAIL.
- [ ] **Step 3: Implement** a tela e a navegação (tema e tokens de cor existentes; sem gráficos).
- [ ] **Step 4: Run** `cd painel && npx vitest run && npm run build` → tudo verde, build ok.
- [ ] **Step 5: Commit** `feat(painel): tela Atividades`.

---

### Task 6: SOUL, ADR-033, runbook e BACKLOG (sem instalar)

**Files:**
- Modify: `deploy/hermes/SOUL.md`, `docs/runbook.md` (seção `{#atividades}`), `docs/BACKLOG.md` (item novo), `docs/STATUS.md`
- Create: `docs/adr/033-atividades.md`
- Test: `tests/mcp/test_hermes.py`, `tests/mcp/test_confiabilidade.py`

**Interfaces:**
- Consumes: Task 4 (nomes das ferramentas).
- Produces: SOUL com uma linha em "Onde achar:" mapeando frases (`"lembra de"`, `"anota aí"`, `"preciso fazer"`) para `atividade_criar`; `atividade_concluir` para `"já fiz"`; `atividade_adiar` para `"deixa para"`; e a regra de que atividade criada é confirmada numa linha com a data entendida, sem pedir sim antes e sem reabrir (para voltar, cria de novo). Runbook `#atividades` no formato do `#despesas`: backup do banco (`gabi.db.antes-atividades-<data>`), `sudo ~/instalar-brain.sh` (migração 0086), **escopo no token do Hermes** (`python -m gabi.mcp.tokens listar` para ver o id e os escopos atuais, depois `escopos <id> <os atuais>,atividades`), backup do `config.yaml` (`config.yaml.bak-antes-atividades`), include com 60 ferramentas, SOUL, restart do `hermes-gateway` e do serviço do MCP, `/new` no Telegram e no WhatsApp, teste: criar com hora 20 min à frente e esperar o aviso no Telegram. BACKLOG: item `AV1` (R) com o teste de aceite do runbook.

- [ ] **Step 1: Write the failing tests**: em `test_hermes.py`, o SOUL cita `atividade_criar`, `atividade_concluir` e `atividade_adiar` em "Onde achar:" com as frases acima e proíbe reabrir; em `test_confiabilidade.py`, a linha do SOUL de atividades menciona `atividade_criar` e "reabrir".
- [ ] **Step 2: Run** `.venv/bin/pytest tests/mcp/test_hermes.py tests/mcp/test_confiabilidade.py -q` → FAIL.
- [ ] **Step 3: Implement** SOUL, ADR-033 (decisão: tabela própria, avisos pelo produtor existente com precisão de 15 min, só Telegram entrega, sem recorrência/insistência, sem reabrir), runbook, BACKLOG e STATUS.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` (leia o resumo, não o exit code) e `cd painel && npx vitest run && npm run build` → tudo verde.
- [ ] **Step 5: Commit** `docs: ADR-033, runbook e SOUL de atividades`. Parar aqui: pedir o ok do Ricardo para merge e instalação.
