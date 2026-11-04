# Convites de agenda recebidos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convite de agenda recebido vira aviso no Telegram e uma decisão de um clique no painel › Envios, com o conflito de horário à vista.

**Architecture:** A sincronização do Graph passa a gravar `resposta`, `organizador_nome` e `serie_id` em `agenda_evento`. O conflito é calculado na leitura. O aviso `convite_agenda` sai pelo produtor existente (`gabi-brain-avisos`). A resposta é um tipo novo de proposta na fila de Envios (`convite_resposta`), que passa pelo mesmo ciclo reservar → enviar → concluir do ADR-024.

**Tech Stack:** Python 3 + FastAPI + SQLite, MCP, Graph API, painel React/TS (vitest).

**Spec:** `docs/superpowers/specs/2026-11-04-convites-agenda-design.md`

## Global Constraints

- R2: nada sai sem o clique em Enviar no painel › Envios. Ferramenta MCP só propõe.
- ADR-023: sem tabela, timer ou unit novos (a migração só altera `agenda_evento` e recria `envio_proposta` com o `check` ampliado).
- Privacidade: não guardar e-mails de outros participantes; do organizador só o nome.
- Escopo: só convites recebidos, só contas de `envios.contas_agenda` (hoje `resper@ness.com.br`, Graph). Respostas: `aceitar|talvez|recusar`, sem comentário. Sem Google, sem Telegram interativo.
- Erros e logs: só códigos fixos; nunca título, nome ou corpo do provedor.
- Migração = `0088` (a última na main é a 0087). Se `feat/projetos-melhorias` criar migração antes, renumerar.
- Comandos: `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check gabi tools tests`, `cd painel && npx vitest run && npm run build`.

## Divergências da spec (confirmar na revisão do plano)

1. **Token:** a spec diz "conta delegada", mas a agenda da ness já é escrita com o **token de aplicativo** (`fonte._token`, `Calendars.ReadWrite`, como `evento_criar`). `accept`/`tentativelyAccept`/`decline` usam o mesmo token e a mesma URL `/users/{conta}/events/{id}/…`. Não precisa de login novo.
2. **Idempotência:** essas três chamadas não aceitam `transactionId`. A proteção contra duplicar é a de sempre: uma tentativa só, 5xx vira `incerto` e nunca repete. Responder duas vezes é inofensivo.
3. **Estado "obsoleta":** `envio_proposta.estado` não tem esse valor. 404/409 do Graph viram `falhou` com `motivo='convite_obsoleto'`, sem repetir o envio. A série não encontrada cai no mesmo código.
4. **Graph devolve 202 sem corpo** nessas chamadas, e o `_pedir` atual trata corpo vazio como "resposta inválida". A task 4 resolve isso.
5. **`declined` nunca fica gravado:** `_recusado_por_mim` já apaga o evento recusado na sincronização. O valor existe só no mapeamento.

## Review Focus

- Convite que ele organiza (`resposta` vazio) nunca vira aviso, convite pendente nem proposta.
- Evento passado ou de dia inteiro: sem aviso e sem proposta.
- Convite pendente que muda de horário avisa de novo; o mesmo horário nunca repete.
- Evento marcado "livre" ou de dia inteiro não conta como conflito; encostar (fim = início) também não.
- Proposta duplicada para o mesmo convite (pendente ou enviando) é recusada; depois de falhar ou vencer, pode propor de novo.
- Convite já respondido no Outlook entre o aviso e o clique: `falhou/convite_obsoleto`, sem erro 500 no painel.

---

## File Structure

- Create `migrations/0088_convites_agenda.sql`: colunas novas e `envio_proposta` recriada.
- Create `gabi/agenda/convites.py`: regras de convite (pendentes, conflito, texto do aviso). Uma responsabilidade, sem rede.
- Modify `gabi/fontes/graph_ness.py`: `_evento` devolve os 3 campos.
- Modify `gabi/agenda/sincronizar.py`: grava os 3 campos.
- Modify `gabi/avisos.py` e `gabi/rotas/avisos.py`: aviso `convite_agenda`.
- Modify `gabi/fontes/graph_ness_envios.py`, `gabi/fontes/graph_ness.py`, `gabi/fontes/ponte.py`: `convite_responder`.
- Modify `gabi/envios/propostas.py` e `gabi/envios/enviar.py`: tipo `convite_resposta`.
- Modify `gabi/mcp/ferramentas_envios.py` e `gabi/mcp/servidor.py`: `propor_resposta_convite`.
- Modify `gabi/rotas/envios.py`: rotas `convites`.
- Modify `painel/src/telas/Envios.tsx`: lista de convites e cartão do tipo novo.
- Create `docs/adr/035-convites-agenda.md`; modify `docs/runbook.md`, `docs/fontes/hermes.md`, `docs/api.md`, `docs/BACKLOG.md`.

---

### Task 1: Migração 0088

**Files:**
- Create: `migrations/0088_convites_agenda.sql`
- Test: `tests/test_migracao_convites.py`

**Interfaces:**
- Produces: `agenda_evento.resposta text`, `agenda_evento.organizador_nome text`, `agenda_evento.serie_id text` (todos nulos nos eventos antigos); `envio_proposta.tipo` aceita `'convite_resposta'`.

- [ ] **Step 1: Write the failing test** (`tests/test_migracao_convites.py`; use a fixture de banco migrado do `conftest.py`)
  - `test_agenda_evento_tem_as_tres_colunas`: `pragma table_info(agenda_evento)` contém `resposta`, `organizador_nome`, `serie_id`.
  - `test_envio_proposta_aceita_convite_resposta`: insert com `tipo='convite_resposta'` funciona; `tipo='x'` levanta `IntegrityError`.
  - `test_migracao_preserva_propostas_existentes`: aplica as migrações até a 0087, insere uma proposta `evento`, aplica a 0088, a linha continua igual (use `migrar` com pasta temporária, padrão de `tests/test_migracao_simplificacao.py`).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_migracao_convites.py -v`. Expected: FAIL.
- [ ] **Step 3: Write `0088_convites_agenda.sql`.** `alter table agenda_evento add column` ×3. Recriar `envio_proposta` (SQLite não altera `check`): `create table envio_proposta_nova` com o mesmo esquema da 0076 e o `tipo` ampliado, `insert … select`, `drop table envio_proposta`, `alter table … rename`, recriar o índice `envio_proposta_estado`. Cabeçalho com o "desfazer" (como a 0087).
- [ ] **Step 4: Run** o teste e `.venv/bin/python -m pytest tests/envios tests/test_db.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): migração 0088 (resposta, organizador, série; tipo convite_resposta)`.

---

### Task 2: Sincronização grava resposta, organizador e série

**Files:**
- Modify: `gabi/fontes/graph_ness.py` (`_evento`, ~linha 599)
- Modify: `gabi/agenda/sincronizar.py` (insert/upsert, ~linhas 85-93)
- Test: `tests/fontes/test_graph_ness.py`, `tests/agenda/test_sincronizar.py`

**Interfaces:**
- Consumes: colunas da task 1.
- Produces: `_evento(item)` ganha as chaves `resposta`, `organizador_nome`, `serie_id`. `resposta` ∈ `needsAction|accepted|tentative|declined|None`.

- [ ] **Step 1: Write the failing tests**
  - `test_evento_graph_mapeia_resposta`: `responseStatus.response` `notResponded` e `none` → `needsAction`; `accepted` → `accepted`; `tentativelyAccepted` → `tentative`; `declined` → `declined`; `organizer` ou `isOrganizer: true` → `None`; ausente → `None`.
  - `test_evento_graph_organizador_so_o_nome`: `organizer.emailAddress.name` vira `organizador_nome`; o endereço não aparece em nenhuma chave do dict.
  - `test_evento_graph_serie`: `seriesMasterId` vira `serie_id`; ausente → `None`.
  - `test_sincronizar_grava_os_tres_campos_e_atualiza_no_upsert` (em `test_sincronizar.py`): grava `needsAction`, depois reprocessa com `accepted` e a linha muda. Evento sem os campos (Google) fica com `None`.
- [ ] **Step 2: Run** esses testes. Expected: FAIL.
- [ ] **Step 3: Implement.** Em `_evento`, os três campos; `organizador_nome` só se for `str`. Em `sincronizar_fonte`, as 3 colunas no `insert` e no `do update set`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/fontes/test_graph_ness.py tests/agenda -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): sincronização do Graph guarda resposta, organizador e série`.

---

### Task 3: Regras de convite (pendentes e conflito)

**Files:**
- Create: `gabi/agenda/convites.py`
- Test: `tests/agenda/test_convites.py`

**Interfaces:**
- Consumes: `agenda_evento` (task 1), `gabi.agenda.tempo.se_sobrepoem`/`Janela`/`para_local`, `gabi.agenda.consulta.fuso_da_agenda`, `propostas.contas_agenda`.
- Produces:
  - `pendentes(con, agora: dt.datetime) -> list[dict]`: cada item `{evento_id: int, conta: str, titulo: str, inicio_utc: str, fim_utc: str, organizador_nome: str | None, serie_id: str | None, conflita_com: list[str]}`, ordenado por início. `conflita_com` = títulos dos eventos em conflito.
  - `texto_aviso(item: dict, fuso: str) -> str`: `"<título> · qui 15h–16h · de <organizador> · conflita com <evento>"` ou `"… · sem conflito"`. Sem organizador, omite o trecho `de …`.

Regras: convite pendente = `resposta='needsAction'`, `inicio_utc > agora`, `dia_inteiro=0`, fonte com `estado='sim'` e conta em `envios.contas_agenda`. Conflito = outro evento (qualquer fonte liberada) com `dia_inteiro=0`, `livre=0`, `resposta` em `accepted`, `needsAction` ou nulo (nulo = ele organiza, ou Google), sobreposto por instante. Encostar não é conflito.

- [ ] **Step 1: Write the failing tests** (fixtures com uma fonte `agenda_fonte` liberada e eventos inseridos direto)
  - `test_pendente_so_needs_action_futuro`: aceito, passado, dia inteiro e organizado por ele ficam de fora.
  - `test_pendente_ignora_conta_fora_de_contas_agenda`.
  - `test_conflito_com_aceito_pendente_e_proprio`: os três contam.
  - `test_nao_conflita_livre_dia_inteiro_tentativo_nem_encostando`.
  - `test_texto_aviso_com_e_sem_conflito_e_sem_organizador`: textos exatos da spec; hora em Brasília (`15h–16h` quando os minutos são zero, `15h30–16h` caso contrário).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/agenda/test_convites.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `pendentes` e `texto_aviso`.
- [ ] **Step 4: Run** o teste. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): convites pendentes e conflito calculado na leitura`.

---

### Task 4: Aviso `convite_agenda`

**Files:**
- Modify: `gabi/avisos.py` (`gerar_avisos`, `TIPOS_REVALIDADOS`, `revalidar`, `UMA_VEZ`)
- Modify: `gabi/rotas/avisos.py` (`_descrever`)
- Test: `tests/test_avisos.py` (ou arquivo novo `tests/test_avisos_convites.py`), `tests/rotas/test_avisos_api.py`

**Interfaces:**
- Consumes: `convites.pendentes`, `convites.texto_aviso`.
- Produces: aviso tipo `convite_agenda`, `chave = f"{evento_id}:{inicio_utc}"`, payload `{evento_id, titulo, inicio_utc, texto}`.

Decisões: a chave leva o horário, então horário novo = chave nova = avisa de novo; mesmo horário nunca repete (entra em `UMA_VEZ`). Revalida: `RESOLVIDO` se a linha sumiu, se `resposta != 'needsAction'` ou se o início mudou; assim um aviso não entregue some quando ele responde no Outlook. A descrição na rota devolve `("Convite: " + titulo, texto + " · painel › Envios")`.

- [ ] **Step 1: Write the failing tests**
  - `test_convite_pendente_gera_um_aviso_com_o_texto_da_spec`.
  - `test_mesmo_convite_nao_avisa_de_novo_nem_no_dia_seguinte`.
  - `test_convite_com_horario_novo_avisa_de_novo`.
  - `test_convite_respondido_fecha_o_aviso_aberto` (revalidar devolve `RESOLVIDO`).
  - `test_convite_organizado_por_ele_nao_gera_aviso`.
  - API: `GET /api/v1/avisos` mostra título `Convite: …`.
- [ ] **Step 2: Run** esses testes. Expected: FAIL.
- [ ] **Step 3: Implement** o laço em `gerar_avisos` depois do de projetos: `for i in convites.pendentes(con, agora): novo("convite_agenda", f"{i['evento_id']}:{i['inicio_utc']}", {...})`; as três mudanças de tabela e a descrição.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_avisos.py tests/test_avisos_antecipados.py tests/rotas/test_avisos_api.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): aviso convite_agenda com conflito`.

---

### Task 5: Graph responde ao convite

**Files:**
- Modify: `gabi/fontes/graph_ness_envios.py` (nova `convite_responder`; atualizar o docstring que hoje diz "não responde")
- Modify: `gabi/fontes/graph_ness.py` (método em `GraphNess`)
- Modify: `gabi/fontes/ponte.py` (`PERMITIDOS["graph_ness"]` e `PonteGraph.convite_responder`)
- Test: `tests/fontes/test_graph_ness_envios.py`, `tests/fontes/test_ponte.py`

**Interfaces:**
- Produces: `graph_ness_envios.convite_responder(fonte, conta: str, evento_id: str, resposta: str, serie_id: str | None) -> dict` devolve `{"externo_id": <id usado>}`. `resposta` ∈ `aceitar|talvez|recusar`. `GraphNess.convite_responder(conta, chave, evento_id, resposta, serie_id)` e `PonteGraph.convite_responder` com a mesma assinatura (a `chave` entra só para o executor chamar igual ao `evento_criar`; não vai ao Graph).

Mapeamento: `aceitar`→`accept`, `talvez`→`tentativelyAccept`, `recusar`→`decline`. URL `{BASE}/users/{conta}/events/{id}/{acao}` com `id = serie_id or evento_id`, token de app. Corpo `{"sendResponse": true}` (sem `comment`). O Graph responde 202 vazio, então não use o `_pedir` que exige dict: extrair um `_pedir_vazio` (ou parâmetro `aceita_vazio=True`) que aceita 2xx com corpo `None`. `id` validado por regex `^[A-Za-z0-9_=+/-]{1,300}$` e passado por `urllib.parse.quote(safe="")`; fora disso `ErroGraphNess("evento inválido")`. Resposta fora das três: `ErroGraphNess("evento inválido")`.

- [ ] **Step 1: Write the failing tests** (HTTP falso, padrão do `evento_criar`)
  - `test_convite_aceitar_talvez_recusar_chamam_a_url_certa`: confere método `POST`, URL e corpo `{"sendResponse": true}` para as três.
  - `test_convite_de_serie_usa_o_serie_id`.
  - `test_convite_202_sem_corpo_e_sucesso`.
  - `test_convite_404_e_409_levantam_status` (`_ErroStatus` com `.status`), e `5xx` idem.
  - `test_convite_id_invalido_e_conta_nao_autorizada`.
  - Varredura existente `test_envios_so_tem_os_verbos_e_urls_previstos`: continua só com `GET` e `POST`; acrescentar `accept`, `tentativelyAccept` e `decline` às URLs esperadas e manter `/reply`, `/forward`, `/sendMail` proibidos.
  - `test_ponte_graph_permite_convite_responder` e rejeita resposta que não seja `externo_id` string.
- [ ] **Step 2: Run** esses testes. Expected: FAIL.
- [ ] **Step 3: Implement** as quatro peças conforme acima.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/fontes -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): graph_ness_envios.convite_responder (accept, tentativelyAccept, decline)`.

---

### Task 6: Proposta `convite_resposta` no ciclo de envios

**Files:**
- Modify: `gabi/envios/propostas.py` (nova `criar_convite_resposta`; `reservar`)
- Modify: `gabi/envios/enviar.py` (`_chamar`, `_motivo`)
- Test: `tests/envios/test_propostas.py`, `tests/envios/test_enviar.py`, `tests/envios/test_ciclo.py`

**Interfaces:**
- Consumes: `convites.pendentes`-style leitura de `agenda_evento`; `graph.convite_responder` (task 5).
- Produces: `propostas.criar_convite_resposta(con, agora, *, conta: str, evento_id: int, resposta: str) -> dict` com `{id, estado, vence_em, resumo}`. Conteúdo canônico: `{conta, provedor:"graph", evento_id, externo_id, serie_id, titulo, inicio_utc, fim_utc, organizador_nome, resposta, conflita_com}`. `vence_em = min(agora+24h, início)`. `resumo`: `"Responder '<título>' qui 15h–16h: aceitar|talvez|recusar"`.

Erros (`ErroEnvio`, códigos fixos): `conta_nao_permitida`; `requisicao_invalida` (resposta fora das três, evento inexistente ou fora da conta); `inicio_passado`; `convite_nao_pendente` (é organizador, já respondido ou dia inteiro); `proposta_duplicada` (já existe proposta `convite_resposta` em `pendente`/`enviando` para o mesmo `evento_id`).
Em `reservar`: tipo `convite_resposta` usa a mesma checagem de conta que `evento`. Em `enviar._chamar`: `graph.convite_responder(l["conta"], l["chave"], c["externo_id"], c["resposta"], c["serie_id"])` (provedor diferente de `graph` → `None`, vira `fonte_indisponivel`). Em `_motivo`: status 404 ou 409 num `convite_resposta` → `("falhou", "convite_obsoleto")`; o resto segue a regra atual (outros 4xx `falhou`, 5xx `incerto`). Para isso `_motivo` recebe o tipo.

- [ ] **Step 1: Write the failing tests**
  - Propostas: criar com sucesso (conteúdo e `vence_em` certos, `conflita_com` preenchido); `conta_nao_permitida`; evento passado; organizador (`resposta` nulo); já aceito; dia inteiro; duplicada; **depois de `falhou` pode propor de novo**; resposta inválida.
  - Ciclo: `reservar` de `convite_resposta` com conta fora da lista → `falhou/conta_nao_permitida`.
  - Enviar (graph falso): sucesso → `enviada` com `externo_id`; 404 → `falhou/convite_obsoleto`; 409 → idem; 500 → `incerto/provedor_500` sem repetir (graph chamado uma vez); 403 → `falhou/provedor_403`.
  - Série: a proposta de um evento com `serie_id` leva o `serie_id` ao graph.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/envios -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as três mudanças.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/envios -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): proposta convite_resposta no ciclo de envios`.

---

### Task 7: Ferramenta MCP `propor_resposta_convite`

**Files:**
- Modify: `gabi/mcp/ferramentas_envios.py` (ESCOPOS, `_MENSAGENS`, nova ferramenta)
- Modify: `gabi/mcp/servidor.py` (`ESCOPOS_FERRAMENTAS`, `FONTES_DA_FERRAMENTA`)
- Modify: `docs/fontes/hermes.md` (regerar com `python -m tools.gerar_hermes`)
- Test: `tests/mcp/test_envios.py`, `tests/mcp/test_servidor.py`, `tests/mcp/test_hermes.py`

**Interfaces:**
- Consumes: `propostas.criar_convite_resposta`.
- Produces: `propor_resposta_convite(conta: str, evento_id: int, resposta: str) -> dict` (escopo `envios`, fonte `()`), devolve o resultado da proposta + `link` (`_com_link`). Mensagens fixas para os códigos novos (`convite_nao_pendente`: "esse convite já foi respondido ou é seu"; `proposta_duplicada`: "já existe uma proposta para esse convite no painel"; `inicio_passado` já existe). Docstring diz que só propõe e que o envio sai no clique.

- [ ] **Step 1: Write the failing tests** (padrão de `tests/mcp/test_envios.py`)
  - `test_propor_resposta_convite_cria_pendente_com_link`.
  - Organizador recusado (`convite_nao_pendente`); conta fora da lista (`conta_nao_permitida`); evento passado (`inicio_passado`); duplicada (`proposta_duplicada`).
  - `test_servidor.py`: `NOVAS_ENVIOS` e a lista esperada incluem `propor_resposta_convite`; contagem de ferramentas sobe de 1.
  - `test_hermes.py` passa com a lista regerada.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/mcp -q`. Expected: FAIL.
- [ ] **Step 3: Implement** a ferramenta e as entradas nos dois dicionários; rodar `.venv/bin/python -m tools.gerar_hermes`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/mcp -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): ferramenta MCP propor_resposta_convite`.

---

### Task 8: Rotas da API

**Files:**
- Modify: `gabi/rotas/envios.py`
- Test: `tests/rotas/test_envios.py`

**Interfaces:**
- Consumes: `convites.pendentes`, `propostas.criar_convite_resposta`, `propostas.listar`.
- Produces (só `boss`):
  - `GET /api/v1/envios/convites` → `{"itens": [{evento_id, conta, titulo, inicio_utc, fim_utc, organizador_nome, conflita_com, proposta_id | null}]}` (`proposta_id` = proposta aberta para o convite, se houver).
  - `POST /api/v1/envios/convites/{evento_id}/propor` com `{"conta": str, "resposta": "aceitar|talvez|recusar"}` → `{id, estado:"pendente", vence_em, resumo}`. Mapa de erros: `proposta_duplicada` e `convite_nao_pendente` → 409; os demais pelo `_erro` existente (400/409).
- Declarar as rotas `/convites` antes das `/{envio_id}/…` (caminhos distintos, mas mantém a leitura simples).

- [ ] **Step 1: Write the failing tests**
  - Lista mostra convite pendente com conflito e `proposta_id` nulo; depois de propor, vem com o id.
  - `POST …/propor` cria a proposta e aparece em `GET /api/v1/envios`; segunda chamada → 409 `proposta_duplicada`.
  - Corpo sem `resposta` ou resposta inválida → 400; não-boss → 403 (padrão da matriz de acesso: ver `tests/test_matriz_acesso.py`, acrescentar as duas rotas).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/rotas/test_envios.py tests/test_matriz_acesso.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** as duas rotas e os códigos novos em `MENSAGENS`/`CONFLITOS`.
- [ ] **Step 4: Run** os mesmos testes. Expected: PASS.
- [ ] **Step 5: Commit** `feat(convites): rotas de convites em /api/v1/envios`.

---

### Task 9: Painel › Envios

**Files:**
- Modify: `painel/src/telas/Envios.tsx`
- Test: `painel/tests/envios.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/envios/convites`, `POST /api/v1/envios/convites/{evento_id}/propor`, e o tipo `convite_resposta` em `GET /api/v1/envios`.
- Produces: bloco **"Convites recebidos · N"** acima de "Esperando seu OK". Cada convite mostra título, `periodo(...)`, "de <organizador>" e `Conflita com <evento>` ou "Sem conflito", e três botões **Aceitar**, **Talvez**, **Recusar** (`aria-label` `Aceitar convite <título>` etc.). O clique cria a proposta e recarrega as duas listas: o convite passa a mostrar "Proposta enviada para o OK" e o cartão novo aparece em "Esperando seu OK", onde o **Enviar** de sempre decide. Cartão `convite_resposta`: rótulo "Responder convite", corpo com título, período, resposta ("Aceitar" / "Talvez" / "Recusar"), aviso de conflito.

- [ ] **Step 1: Write the failing tests** (padrão de `envios.test.tsx`)
  - Lista de convites com conflito e sem conflito (textos exatos).
  - Clicar Aceitar chama o POST com `{conta, resposta:"aceitar"}` e recarrega.
  - Convite com `proposta_id` mostra "Proposta enviada para o OK" e sem botões.
  - Erro 409 `proposta_duplicada` mostra o aviso de erro e relê as listas.
  - Cartão `convite_resposta` na fila mostra título, período e a resposta.
  - Sem convites: bloco some (sem "Convites recebidos").
- [ ] **Step 2: Run** `cd painel && npx vitest run tests/envios.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** o componente `Convites` (usa `useApi`, `useAcao`, `Bloco` como o resto da tela) e o ramo `convite_resposta` em `Corpo` e `TIPOS`.
- [ ] **Step 4: Run** `cd painel && npx vitest run && npm run build`. Expected: PASS e build ok.
- [ ] **Step 5: Commit** `feat(convites): lista de convites e cartão de resposta no painel`.

---

### Task 10: ADR-035, runbook, docs e verificação final

**Files:**
- Create: `docs/adr/035-convites-agenda.md`; modify `docs/adr/README.md`
- Modify: `docs/runbook.md` (seção `#envios`: passos de instalação), `docs/api.md`, `docs/BACKLOG.md`, `docs/STATUS.md`, `deploy/hermes/SOUL.md`

- [ ] **Step 1: ADR-035.** Amplia o ADR-024 a "responder convite recebido" (R2 mantida: só no clique); decisões e as 5 divergências desta página resolvidas; fora do escopo (comentário, outro horário, Google, Telegram interativo); desfazer (backup do banco, `git revert`, `sudo ~/instalar-brain.sh`; a migração 0088 traz o SQL de desfazer).
- [ ] **Step 2: Runbook `#envios`.** Passos do dono, nesta ordem: backup do banco; `sudo ~/instalar-brain.sh`; pôr `propor_resposta_convite` no include do Hermes (lista em `docs/fontes/hermes.md`, nova contagem); SOUL novo (`bash ~/gabi-brain/deploy/instalar-hermes-soul.sh`) com uma linha: "convite recebido: proponha com `propor_resposta_convite` e diga que ele decide no painel"; `sudo systemctl restart hermes-gateway`; `/new` no Telegram e no WhatsApp; teste real (o Hermes propõe, ele clica Enviar). `docs/api.md`: as duas rotas. BACKLOG: item CV1 "convites de agenda: instalar e teste real".
- [ ] **Step 3: Verificação completa, lendo o resumo (não só o exit code).**
  - `.venv/bin/python -m pytest -q`. Expected: resumo sem `failed` nem `error`.
  - `.venv/bin/ruff check gabi tools tests`. Expected: sem erros.
  - `cd painel && npx vitest run && npm run build`. Expected: sem falhas.
- [ ] **Step 4: Commit** `docs(convites): ADR-035, runbook, api e backlog`.

Nada é mergeado nem instalado sem o ok explícito do Ricardo.
