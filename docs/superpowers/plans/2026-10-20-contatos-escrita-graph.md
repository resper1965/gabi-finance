# Escrita de contatos da ness no Graph — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O brain propõe criar/corrigir contatos da `resper@ness.com.br` no Graph e só grava o que o dono aprova no painel.

**Architecture:** Leitura guarda `graph_id` e telefone original em `contato_graph`; um gerador sem modelo grava propostas em `contato_proposta`; o painel aprova; `gabi.escuta.contatos_gravar` aplica as aprovadas pela ponte `graph_ness`, que ganha só `contato_criar`/`contato_corrigir` (módulo próprio, sem DELETE). Interruptor `contatos.escrita` nasce desligado.

**Tech Stack:** Python 3 + FastAPI + SQLite (pytest), React/Vite no `painel/` (vitest), systemd.

**Spec:** `docs/superpowers/specs/2026-10-20-contatos-escrita-graph-design.md`

## Global Constraints
- Escrita só em `displayName` e `mobilePhone`; nenhum DELETE; só contas de `M365_CONTAS`; id do contato validado por `^[A-Za-z0-9_=-]{8,400}$`.
- Interruptor `contatos.escrita` (`parametro`, JSON `"ligado"`/`"desligado"`), padrão `desligado`.
- Auditoria e logs: id da proposta, tipo e login; nunca nome nem telefone.
- Aprovação só pelo painel (rotas `exigir("boss")`); Hermes/MCP não aprovam.
- Migração nova é a `0072` (a última é `0071_teams.sql`). `gabi/fontes/graph_ness.py` NÃO ganha as palavras `PATCH`, `PUT`, `DELETE` nem um terceiro `"POST"` (testes `test_so_leitura_no_codigo_fora_do_move` e `test_so_dois_posts...` continuam valendo).
- Dado em `parametro`/banco, nunca chumbado (regra do projeto).

## Review Focus
- Contato editado pelo dono entre a proposta e a aplicação → descartar, nunca sobrescrever.
- Proposta recusada com o mesmo valor não volta; com valor novo, volta.
- Contato sem nome ou sem telefone no Graph (só e-mail) não gera `corrigir`.
- Número aprovado sem nome na escuta não gera `criar`.
- Falha do Graph em uma proposta não aborta as outras e não deixa `aprovada` presa para sempre.

---

### Task 1: Guardar `graph_id` e telefone original na leitura
**Files:**
- Create: `migrations/0072_contato_escrita.sql`
- Modify: `gabi/fontes/graph_ness.py:228-252` (`contatos` inclui `graph_id`), `gabi/escuta/contatos.py` (`sincronizar` grava `contato_graph`)
- Test: `tests/fontes/test_graph_ness.py`, `tests/escuta/test_contatos.py`

**Interfaces:**
- Produces: tabelas `contato_graph(conta text, graph_id text, nome text, telefone_original text, telefone text null, atualizado_em text, primary key(conta, graph_id, telefone_original))` e `contato_proposta(id integer primary key, tipo text check in ('criar','corrigir'), conta text, graph_id text null, nome_antes text null, telefone_antes text null, nome_depois text, telefone_depois text, origem text check in ('whatsapp','telefone_invalido'), estado text check in ('pendente','aprovada','recusada','aplicada','falhou') default 'pendente', motivo text null, criada_em text, decidida_em text null, decidida_por text null, aplicada_em text null)` com índice único parcial `(conta, tipo, coalesce(graph_id,''), telefone_depois) where estado in ('pendente','aprovada')`. Itens de `GraphNess.contatos` ganham `"graph_id": str`.

- [ ] **Step 1: Failing tests.** Em `test_graph_ness.py`: `test_contatos_trazem_graph_id` (resposta com `{"id": "AAMk1234", ...}` → cada item tem `graph_id == "AAMk1234"`). Em `test_contatos.py`: `test_sincronizar_guarda_graph_id_e_telefone_original` (item `{"nome":"Ana","telefone":"11 9999-0000","graph_id":"AAMk1234"}` → linha em `contato_graph` com `telefone_original == "11 9999-0000"`, `telefone` o E.164 de `_telefone`), `test_telefone_invalido_fica_com_telefone_nulo` (ramal → `telefone is None`), `test_sincronizar_substitui_so_a_conta` (releitura troca as linhas da conta; item Google sem `graph_id` não entra).
- [ ] **Step 2:** `pytest tests/fontes/test_graph_ness.py tests/escuta/test_contatos.py -q` → FAIL.
- [ ] **Step 3: Implement** a migração (esquema acima); `contatos()` acrescenta `graph_id` (id do contato, só se for str que casa `_ID_CONTATO`); em `sincronizar`, para itens com `graph_id`, `delete from contato_graph where conta=?` e reinsere dentro da mesma transação das linhas atuais (mesma regra de "falha não apaga").
- [ ] **Step 4:** mesmos testes → PASS; `pytest tests/test_esquema.py -q` PASS.
- [ ] **Step 5: Commit** `feat(contatos): guarda graph_id e telefone original da ness`.

### Task 2: Escrita na ponte `graph_ness`
**Files:**
- Create: `gabi/fontes/graph_ness_contatos.py`
- Modify: `gabi/fontes/graph_ness.py` (dois métodos finos), `gabi/fontes/ponte.py:26-30` (`PERMITIDOS`) e `PonteGraph`
- Test: `tests/fontes/test_graph_ness_contatos_escrita.py`

**Interfaces:**
- Produces: em `graph_ness_contatos.py`: `criar(gr, conta, nome, telefone) -> dict` (`{"id": str}`), `corrigir(gr, conta, graph_id, antes, depois) -> dict` (`{"resultado": "ok"|"alterado"}`; `antes`/`depois` = `{"nome": str, "telefone": str}`; relê `GET /users/<conta>/contacts/<id>?$select=displayName,mobilePhone` e devolve `alterado` sem escrever se `displayName` ≠ `antes["nome"]` ou `mobilePhone` ≠ `antes["telefone"]` original). `GraphNess.contato_criar(conta, nome, telefone)` e `GraphNess.contato_corrigir(conta, graph_id, antes, depois)` delegam (import dentro do método, evita ciclo). `PonteGraph.contato_criar/contato_corrigir` validam o formato da resposta (`ErroGraphNess("resposta inválida do serviço de fontes")`).
- Consumes: `_chamar`, `HOST`, `BASE`, `ErroGraphNess`, `gr._token`, `gr._http`, `gr._conta`.

- [ ] **Step 1: Failing tests** (HTTP falso como em `test_graph_ness.py::_http`): `test_criar_faz_post_so_com_displayname_e_mobilephone` (URL `…/users/resper%40ness.com.br/contacts`, corpo JSON com exatamente essas duas chaves), `test_corrigir_so_patch_apos_reler_sem_mudanca`, `test_corrigir_contato_alterado_nao_escreve` (relida diferente → `{"resultado":"alterado"}` e nenhum PATCH nas chamadas), `test_conta_fora_da_lista_recusada_sem_http`, `test_id_invalido_recusado` (`"../x"`, `"a b"`), `test_401_invalida_token_e_repete_uma_vez`, `test_nome_ou_telefone_vazio_recusado`, `test_trava_no_modulo`: o texto de `graph_ness_contatos.py` não contém `DELETE`/`PUT`, o de `graph_ness.py` não contém `PATCH`; `not hasattr(GraphNess, "contato_apagar")`.
- [ ] **Step 2:** rodar o arquivo → FAIL.
- [ ] **Step 3: Implement** o módulo (um helper `_escrever(gr, metodo, url, corpo) -> tuple[int, object]` com a mesma regra de 401/repetir de `_enviar_mover`; status ≥ 300 → `ErroGraphNess("contato: HTTP <status>")` sem corpo); incluir os dois nomes em `PERMITIDOS["graph_ness"]`; métodos finos no cliente da ponte.
- [ ] **Step 4:** `pytest tests/fontes -q` → PASS (inclui os testes de trava antigos, que seguem verdes).
- [ ] **Step 5: Commit** `feat(fontes): escrita de contatos da ness (criar/corrigir) pela ponte`.

### Task 3: Gerador de propostas
**Files:**
- Create: `gabi/escuta/contatos_propostas.py`
- Modify: `gabi/escuta/contatos.py` (`main` chama `gerar` depois de `sincronizar`, com a mesma conexão)
- Test: `tests/escuta/test_contatos_propostas.py`

**Interfaces:**
- Produces: `gerar(con, agora: str) -> dict` (`{"criar": n, "corrigir": n}`); `listar(con, estado: str | None = None) -> list[dict]`; `decidir(con, proposta_id: int, estado: str, login: str, agora: str) -> None` (`aprovada`|`recusada`, só a partir de `pendente`; `ErroProposta` caso contrário); `aprovar_correcoes(con, login: str, agora: str) -> int`.
- Consumes: `contato_graph`, `escuta_remetente`, `contato_google`, `contatos._telefone`, `contatos.conta_origem(con)`.

- [ ] **Step 1: Failing tests:** `test_criar_para_remetente_aprovado_com_nome_sem_contato`; `test_nao_cria_sem_nome` (nome nulo/branco); `test_nao_cria_se_numero_ja_e_contato_ness_ou_google`; `test_corrigir_quando_original_invalido_vira_valido` (`"11 9999-0000"` com `telefone` nulo → proposta `corrigir` com `telefone_depois == _telefone({"telefone": original})`); `test_nao_corrige_se_a_regra_nao_produz_numero` (ramal); `test_nao_corrige_contato_sem_nome`; `test_recusada_nao_repete_mesmo_valor_e_repete_valor_novo`; `test_gerar_e_idempotente` (duas rodadas, uma proposta); `test_decidir_so_de_pendente`; `test_aprovar_correcoes_so_do_tipo_corrigir`.
- [ ] **Step 2:** FAIL. **Step 3: Implement** conforme a spec ("Gerador"); `decidir` grava `decidida_em`/`decidida_por`. **Step 4:** PASS (`pytest tests/escuta -q`).
- [ ] **Step 5: Commit** `feat(contatos): gerador de propostas de criar/corrigir contato`.

### Task 4: Aplicação das aprovadas + interruptor + timer
**Files:**
- Create: `gabi/escuta/contatos_gravar.py`
- Modify: `deploy/gabi-brain-contatos.service` (acrescentar `ExecStartPost=/opt/gabi-brain/venv/bin/python -m gabi.escuta.contatos_gravar`; sem mudar sandbox: continua só AF_UNIX), `tests/test_deploy.py` se checar linhas da unit
- Test: `tests/escuta/test_contatos_gravar.py`

**Interfaces:**
- Produces: `escrita_ligada(con) -> bool` (`parametro` `contatos.escrita == "ligado"`); `aplicar(con, graph, agora: str) -> dict` (`graph` = objeto com `contato_criar`/`contato_corrigir`; devolve contagens `{"aplicadas","falhas","descartadas","simuladas"}`); `main(banco=None, *, graph=None) -> int` (usa `PonteGraph(GABI_FONTES_SOCKET)`; imprime só contagens).
- Consumes: Task 2 (`contato_criar`, `contato_corrigir`) e Task 3 (`contato_proposta`).

- [ ] **Step 1: Failing tests (fake `graph` com lista de chamadas):** `test_desligado_nao_grava_e_conta_simuladas`; `test_ligado_aplica_so_aprovadas`; `test_criar_marca_aplicada_e_insere_em_contato_graph_com_o_id_devolvido`; `test_corrigir_ok_atualiza_contato_graph`; `test_contato_alterado_vira_falhou_com_motivo_contato_alterado_e_nao_fica_aprovada`; `test_erro_do_graph_em_uma_nao_aborta_as_outras` (motivo sem nome/telefone: assert que `motivo` não contém o nome); `test_main_sem_socket_retorna_2`; `test_main_sai_0_quando_nada_a_fazer`.
- [ ] **Step 2:** FAIL. **Step 3: Implement** conforme "Aplicação" da spec; `motivo` curto fixo (`contato_alterado`, `graph_indisponivel`, `rejeitado`). **Step 4:** `pytest tests/escuta/test_contatos_gravar.py tests/test_deploy.py -q` PASS.
- [ ] **Step 5: Commit** `feat(contatos): aplica propostas aprovadas no Graph (interruptor desligado por padrão)`.

### Task 5: Rotas da API
**Files:**
- Modify: `gabi/rotas/escuta.py` (junto de `/contatos`, linha ~269), docs geradas (`docs/api.md`, `docs/openapi.json`), amostras (`painel/tests/amostras`)
- Test: `tests/rotas/test_escuta.py`

**Interfaces:**
- Produces: `GET /api/v1/escuta/contatos/propostas?estado=pendente` (envelope com `{"itens": [...], "escrita": "ligado"|"desligado"}`); `POST /api/v1/escuta/contatos/propostas/{id}/decisao` corpo `{"estado": "aprovada"|"recusada"}`; `POST /api/v1/escuta/contatos/propostas/aprovar-correcoes`. Todas `exigir("boss")`; auditoria `escuta: contato proposta <id> → <estado>` (sem nome/telefone).
- Consumes: Task 3.

- [ ] **Step 1: Failing tests:** `test_propostas_listam_e_so_boss` (nível menor → 403), `test_decisao_aprova_e_audita_sem_dados_pessoais` (auditoria não contém nome nem telefone), `test_decisao_em_proposta_ja_decidida_409`, `test_decisao_estado_invalido_400`, `test_aprovar_correcoes_devolve_quantidade`, `test_listar_mostra_estado_do_interruptor`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar; regenerar docs/amostras com `python -m tools.gerar_amostras` e o gerador de `docs/api.md` usado por `tests/test_docs_api.py`. **Step 4:** `pytest tests/rotas tests/test_docs_api.py tests/test_amostras_painel.py tests/test_matriz_acesso.py -q` PASS.
- [ ] **Step 5: Commit** `feat(api): rotas de propostas de contatos`.

### Task 6: Painel (Escuta › Contatos)
**Files:**
- Create: `painel/src/telas/ContatosPropostas.tsx`
- Modify: `painel/src/telas/Escuta.tsx:244` (monta o bloco; troca a nota "Nada é escrito nos contatos." por "Só grava o que você aprovar abaixo."), `gabi/static`/`gabi/painel` (build com `npm run build`)
- Test: `painel/tests/Contatos.test.tsx`

**Interfaces:** Consumes as rotas da Task 5.

- [ ] **Step 1: Failing tests (vitest, com `apiFalsa.ts`):** lista pendentes com antes/depois lado a lado; Aprovar e Recusar chamam `POST …/decisao` com o estado certo e recarregam; "Aprovar todas as correções" chama a rota em lote; com `escrita: "desligado"` mostra o aviso "A gravação está desligada: aprovar não grava ainda"; estado vazio mostra "Nenhuma proposta".
- [ ] **Step 2:** `cd painel && npx vitest run tests/Contatos.test.tsx` → FAIL. **Step 3:** implementar o componente no padrão dos blocos vizinhos (`Bloco`, `Painel`, `agir`). **Step 4:** vitest PASS; `npm run build`; `pytest tests/test_painel.py -q` PASS.
- [ ] **Step 5: Commit** `feat(painel): fila de propostas de contatos`.

### Task 7: ADR-020, docs e runbook
**Files:**
- Create: `docs/adr/020-escrita-contatos-graph.md`
- Modify: `docs/adr/019-graph-ness.md` (uma linha apontando a exceção), `docs/fontes/graph-ness.md` (permissão `Contacts.ReadWrite` agora usada, só para criar/corrigir), `docs/runbook.md` (passo "ligar a escrita de contatos": instalar, sincronizar, revisar a fila, `contatos.escrita` → `"ligado"`), `docs/STATUS.md`

- [ ] **Step 1:** escrever o ADR (contexto, decisão, trava, risco aceito: o app tem permissão no tenant inteiro; a barreira é o código e a aprovação) e as alterações acima. **Step 2:** `pytest -q` completo → tudo verde (anotar o total). **Step 3: Commit** `docs: ADR-020 e runbook da escrita de contatos`.
