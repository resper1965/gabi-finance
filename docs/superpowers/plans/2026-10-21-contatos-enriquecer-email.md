# Enriquecer contatos da ness com e-mail e piso de interação Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propor (com aprovação do Ricardo) acrescentar e-mails do Google aos contatos da ness no Graph e só propor `criar` contato para quem passa o piso de interação.

**Architecture:** Tipo novo `adicionar_email` na fila `contato_proposta` (migração 0074), gerado em `contatos_propostas.gerar`, gravado por `contatos_gravar` via método novo da ponte `graph_ness_contatos.adicionar_email` (PATCH só de `emailAddresses`, revalidando). Módulo novo `gabi/escuta/interacao.py` conta interação em 12 meses e barra `criar` abaixo do piso.

**Tech Stack:** Python 3 / SQLite / FastAPI (`gabi/rotas/escuta.py`) / painel React (`painel/src/telas/ContatosPropostas.tsx`) / pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-contatos-enriquecer-email-design.md` (ADRs anteriores: `docs/adr/020-…`, `docs/adr/021-…`)

## Global Constraints

- Worktree `~/gabi-brain-enriquecer`, branch `feat/contatos-enriquecer`. Nada vai a produção neste plano: merge e `sudo ~/instalar-brain.sh` só com ordem do Ricardo.
- `adicionar_email` só **acrescenta**: nunca troca nem remove e-mail; contato que já tem e-mail → `alterado`.
- Nenhum `DELETE` novo; `graph_ness.py` continua sem PATCH/PUT/DELETE (escrita só em `graph_ness_contatos.py`). O teste `tests/cobrar/test_nibo.py::test_nenhuma_rota_de_exclusao_no_codigo` segue verde.
- Log e saída só com contagens: nunca nome, telefone nem e-mail. Motivos de falha são os fixos de `contatos_gravar.py` (`CONTATO_ALTERADO`, `GRAPH_INDISPONIVEL`).
- Piso de interação: `JANELA_DIAS=365`, `PISO_MENSAGENS=5`, `PISO_RESPOSTAS=1`; passa se `respostas >= 1` ou `mensagens >= 5`.
- Só `adicionar_email` entra em aprovação em lote junto de `corrigir`/`corrigir_nome`; `criar` e `apagar_*` nunca.
- Mensagens e comentários em português, no estilo do código vizinho (docstring curta, sem narrar o óbvio). Commits terminam com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Suíte completa verde antes de qualquer merge (padrão do repo: shards, ver `PROGRESSO-GOAL.md`).

## Review Focus

- E-mail do Google em maiúscula, repetido entre contas ou sem `@`: normalizar (minúsculas), deduplicar e descartar o inválido (Task 3).
- Proposta já `aplicada` ou `recusada` não renasce a cada sincronização, porque o espelho `contato_graph` não guarda e-mail (Task 3).
- Contato com 2 telefones válidos, ou com telefone repetido em outro contato: não gera proposta (Task 3).
- Remetente `Nome <Endereco@X.com>` em maiúscula e resposta fora da janela de 12 meses (Task 5).
- WhatsApp não registra resposta sua em `escuta_msg`: para número, só passa por `mensagens >= 5` (Task 5).

---

### Task 1: Migração 0074 (tipo `adicionar_email`, coluna `email_depois`, origem `google_email`)

**Files:**
- Create: `migrations/0074_contato_proposta_email.sql`
- Test: `tests/escuta/test_contatos_propostas.py` (acrescentar)

**Interfaces:**
- Produces: tabela `contato_proposta` com `tipo` aceitando `'adicionar_email'`, `origem` aceitando `'google_email'` e coluna nova `email_depois text` (nula nos outros tipos); índice `contato_proposta_aberta` recriado igual ao da 0073.

- [ ] **Step 1: Teste que falha** — em `tests/escuta/test_contatos_propostas.py`:
  - `test_migracao_0074_aceita_adicionar_email_e_google_email`: insere em `contato_proposta` (tipo `adicionar_email`, origem `google_email`, `email_depois='a@x.com;b@x.com'`, `telefone_depois=NUM`) e confere que a linha volta com esses valores; um tipo inventado (`'xis'`) levanta `sqlite3.IntegrityError`.
  - `test_migracao_0074_preserva_linhas_e_indice_aberto`: depois do fixture `con`, insere uma proposta `corrigir` pendente, roda de novo `migrar` (idempotente) e confere que a linha continua e que uma segunda `pendente` igual (mesma conta/tipo/graph_id/telefone_depois) levanta `IntegrityError`.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/escuta/test_contatos_propostas.py -k 0074 -q` → FAIL (tipo/coluna não existem).
- [ ] **Step 3: Escrever `migrations/0074_contato_proposta_email.sql`** no mesmo molde da 0073 (recria `contato_proposta_nova`, copia as linhas com a lista de colunas explícita, `drop`, `rename`, recria `contato_proposta_aberta`). Mudanças: `tipo in (…,'adicionar_email')`, `origem in (…,'google_email')`, coluna `email_depois text` depois de `telefone_depois`. Cabeçalho de comentário no estilo da 0073 (como desfazer: só removendo antes as linhas do tipo novo).
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS; `pytest tests/escuta -q -k "contato"` verde.
- [ ] **Step 5: Commit** — `git add migrations/0074_contato_proposta_email.sql tests/escuta/test_contatos_propostas.py && git commit -m "feat(contatos): migração 0074 — tipo adicionar_email"`.

---

### Task 2: Ponte — `adicionar_email`

**Files:**
- Modify: `gabi/fontes/graph_ness_contatos.py` (nova função + docstring do módulo), `gabi/fontes/graph_ness.py` (método `contato_adicionar_email`), `gabi/fontes/ponte.py` (allowlist `graph_ness` em `ponte.py:28-30` e cliente `PonteGraph`, junto de `contato_apagar`, ~`ponte.py:252`)
- Test: `tests/fontes/test_graph_ness_contatos_escrita.py`, `tests/fontes/test_ponte.py`

**Interfaces:**
- Produces: `graph_ness_contatos.adicionar_email(gr, conta, graph_id, nome_antes, telefone_antes, emails) -> {"resultado": "ok"|"alterado"}`; `GraphNess.contato_adicionar_email(conta, graph_id, nome_antes, telefone_antes, emails: list[str]) -> dict`; `PonteGraph.contato_adicionar_email` com a mesma assinatura. `telefone_antes` é o texto original que o Graph guarda (o `telefone_original` do espelho).

- [ ] **Step 1: Testes que falham** em `tests/fontes/test_graph_ness_contatos_escrita.py`, seguindo o fake HTTP já usado ali para `renomear`/`apagar`:
  - `test_adicionar_email_escreve_so_emailaddresses`: GET devolve `displayName`, `mobilePhone`/telefone iguais ao esperado e `emailAddresses: []`; a chamada faz um PATCH com corpo exatamente `{"emailAddresses": [{"address": "a@x.com"}, {"address": "b@x.com"}]}`; resultado `{"resultado": "ok"}`.
  - `test_adicionar_email_alterado_se_nome_mudou`, `..._se_telefone_mudou`, `..._se_ja_tem_email`: GET diverge → `{"resultado": "alterado"}` e **nenhum** PATCH.
  - `test_adicionar_email_valida_entrada`: lista vazia, mais de 5 e-mails, e-mail sem `@` ou com mais de 254 caracteres, `graph_id` fora do padrão → `ErroGraphNess`, sem chamada HTTP.
  - `test_adicionar_email_nunca_usa_delete`: o fake registra os métodos HTTP usados; nenhum `DELETE`.
  Em `tests/fontes/test_ponte.py`: o teste que confere a allowlist/delegação de `contato_*` (ver o de `contato_apagar`, ~linha 489) ganha `contato_adicionar_email`.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/fontes/test_graph_ness_contatos_escrita.py tests/fontes/test_ponte.py -q` → FAIL.
- [ ] **Step 3: Implementar** `adicionar_email(gr, conta, graph_id, nome_antes, telefone_antes, emails) -> dict` em `graph_ness_contatos.py`: `_url_contato` + `_texto` para nome/telefone; valida `emails` (lista de 1 a `MAX_EMAILS=5` strings com `@`, ≤ 254 caracteres, senão `ErroGraphNess("contato inválido")`); GET `?$select=displayName,mobilePhone,homePhones,businessPhones,emailAddresses`; `alterado` se o nome difere, se os telefones atuais (mobile + home + business) não são exatamente `[telefone_antes]`, ou se `emailAddresses` não está vazio; senão `_escrever(gr, "PATCH", url, {"emailAddresses": [{"address": e} for e in emails]})`. Wrapper em `graph_ness.py` no molde de `contato_apagar` (import local); entrada `"contato_adicionar_email"` na allowlist e método no `PonteGraph` no molde de `contato_apagar` (`self._resultado("contato_adicionar_email", …)`). Atualizar a docstring do módulo ("…, APAGAR O CONTATO e ADICIONAR E-MAIL (ADR-022)").
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS; também `pytest tests/cobrar/test_nibo.py -q` (trava de `DELETE`) → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(contatos): ponte adicionar_email (PATCH só de emailAddresses)"`.

---

### Task 3: Geração das propostas `adicionar_email`

**Files:**
- Modify: `gabi/escuta/contatos_propostas.py` (`gerar`, helper novo, constante), `gabi/escuta/contatos.py:~212` (linha `propostas:` do log)
- Test: `tests/escuta/test_contatos_propostas.py`, `tests/escuta/test_contatos.py` (linha do log)

**Interfaces:**
- Consumes: migração da Task 1; tabelas `contato_graph(conta, graph_id, nome, telefone_original, telefone, campo)` e `contato_google_email(conta, email, telefone, nome)`.
- Produces: `nome_compativel(a: str | None, b: str | None) -> bool`; `_emails(con) ` interno; `gerar(con, agora) -> dict` ganha as chaves `"adicionar_email"` (int, propostas novas) e `"revisar"` (int, contatos com e-mail do Google barrados pelos filtros). Proposta gerada: `tipo='adicionar_email'`, `origem='google_email'`, `graph_id` do contato, `nome_antes=nome da ness`, `telefone_antes=telefone E.164`, `nome_depois=nome da ness`, `telefone_depois=telefone E.164`, `email_depois='a@x.com;b@x.com'` (minúsculas, únicos, ordenados).

- [ ] **Step 1: Testes que falham** (helper `_graph` e fixture `con` já existem; criar helper `_gmail(con, email, tel, nome, conta="resper@gmail.com")` que insere em `contato_google_email`):
  - `test_nome_compativel`: `("Ricardo Esper","Esper")` True; `("José da Silva","Jose Silva")` True (sem acento/caixa); `("Ana Lima","Bruno Souza")` False; `(None,"x")` False; só partes de ≥ 3 letras contam e `de/da/do/dos/das` são ignoradas (`("Maria de Souza","Pedro de Lima")` False).
  - `test_gera_adicionar_email_quando_tudo_confere`: contato único com telefone, Google com 2 e-mails (um em maiúscula, um repetido noutra conta) → 1 proposta com `email_depois` em minúsculas, sem repetição, `;`-separada; `r["adicionar_email"] == 1`.
  - `test_nao_gera_com_telefone_repetido_em_outro_contato` (`revisar == 1`), `test_nao_gera_com_nome_sem_parte_comum` (`revisar == 1`), `test_nao_gera_com_dois_telefones_validos`, `test_nao_gera_sem_email_no_google`, `test_descarta_email_sem_arroba`.
  - `test_aplicada_ou_recusada_nao_renasce`: marca a proposta como `aplicada` e gera de novo → 0 novas; idem `recusada`.
  - `test_gerar_devolve_chaves_novas`: o dict de `gerar` tem `adicionar_email` e `revisar` (ajustar `_antigas` se precisar).
  Em `tests/escuta/test_contatos.py`: a linha de log `propostas:` passa a incluir `adicionar_email=N revisar=N` (ver o teste que confere `propostas: criar=`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/escuta/test_contatos_propostas.py tests/escuta/test_contatos.py -q` → FAIL.
- [ ] **Step 3: Implementar.** `nome_compativel` em `contatos_propostas.py` (normaliza com `unicodedata`, tokens `re.findall(r"[a-z]{3,}")`, remove `STOP = {"dos","das","del"}`, interseção não vazia). Novo passo em `gerar`, dentro da mesma `transacao`, depois de `_limpeza`: para cada `(conta, graph_id)` de `contato_graph` com exatamente uma linha `telefone is not null` e esse telefone aparecendo em um só `(conta, graph_id)`; junta e-mails de `contato_google_email` desse telefone (lower/strip, descarta sem `@`, ordena, deduplica); sem e-mail → ignora; nome do Google (qualquer linha) compatível com o do contato, senão `revisar += 1`; telefone repetido ou 2 telefones com e-mail disponível → `revisar += 1`. `_inserir` ganha parâmetro opcional `email=None` gravado em `email_depois` (a dedupe `_ja_decidida` já cobre `aplicada`/`recusada` pela chave `nome_depois`+`telefone_depois`). Atualizar a docstring de `gerar` e `contatos.py` (print `propostas: criar=… adicionar_email=… revisar=…`; só contagens).
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(contatos): gerar propostas adicionar_email com telefone único e nome compatível"`.

---

### Task 4: Gravação (`contatos_gravar`)

**Files:**
- Modify: `gabi/escuta/contatos_gravar.py` (novo aplicador + `APLICADORES`)
- Test: `tests/escuta/test_contatos_gravar.py`

**Interfaces:**
- Consumes: `PonteGraph.contato_adicionar_email(conta, graph_id, nome_antes, telefone_antes, emails)` (Task 2); proposta da Task 3.
- Produces: `_aplicar_adicionar_email(con, graph, p, agora) -> str | None` registrado em `APLICADORES["adicionar_email"]`. Revalida no espelho (linha do contato com `telefone == p["telefone_antes"]`, `nome == p["nome_antes"]`, conta ainda em `contas_contatos`) e passa ao Graph o `telefone_original` dessa linha e `p["email_depois"].split(";")`.

- [ ] **Step 1: Testes que falham** (estender o fake `graph` do arquivo com `contato_adicionar_email` que registra a chamada e devolve `{"resultado": "ok"}` ou o valor configurado):
  - `test_adicionar_email_ok_vira_aplicada_e_chama_a_ponte_com_original`: o fake recebe `graph_id`, `nome_antes`, o `telefone_original` do espelho e a lista `["a@x.com","b@x.com"]`; proposta `aplicada`.
  - `test_adicionar_email_revalida_espelho`: nome mudou no espelho, linha sumiu ou conta fora de `contas_contatos` → `falhou` com motivo `contato_alterado` e **sem** chamar o fake.
  - `test_adicionar_email_alterado_pelo_graph`: fake devolve `{"resultado": "alterado"}` → `falhou`/`contato_alterado`, contado em `descartadas`.
  - `test_adicionar_email_graph_cai`: fake levanta → `falhou`/`graph_indisponivel`.
  - `test_adicionar_email_desligado_nao_chama_o_graph`: `contatos.escrita` desligado → `simuladas`, fake sem chamadas.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/escuta/test_contatos_gravar.py -q` → FAIL.
- [ ] **Step 3: Implementar `_aplicar_adicionar_email`** no molde de `_aplicar_apagar_contato` (mesmo `_resultado_graph` e `_gravar_aplicada`; `local` não altera o espelho porque `contato_graph` não guarda e-mail). Registrar em `APLICADORES`. Atualizar a docstring de módulo (lista de revalidações).
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(contatos): gravar adicionar_email pela ponte, revalidando o espelho"`.

---

### Task 5: Piso de interação e barreira no `criar`

**Files:**
- Create: `gabi/escuta/interacao.py`, `tests/escuta/test_interacao.py`
- Modify: `gabi/escuta/contatos_propostas.py` (`gerar`, ramo `criar`)
- Test: `tests/escuta/test_contatos_propostas.py`

**Interfaces:**
- Produces: `JANELA_DIAS = 365`, `PISO_MENSAGENS = 5`, `PISO_RESPOSTAS = 1`; `interacao(con, agora: str, endereco: str | None = None, telefone: str | None = None) -> dict` → `{"mensagens": int, "respostas": int}`; `passa_piso(r: dict) -> bool`. `gerar` ganha a chave `"abaixo_do_piso"` (int).
- Fontes: e-mail — `email_msg(remetente, recebida_em, lista, classe)` e `email_respondido(endereco, em)`; WhatsApp — `escuta_msg(de, recebida_em)` (antes de codar, conferir em `gabi/escuta/` como `de` é gravado e usar o mesmo formato de `escuta_remetente.numero`). `escuta_msg` não registra resposta do Ricardo: para telefone `respostas` é sempre 0.

- [ ] **Step 1: Testes que falham** em `tests/escuta/test_interacao.py` (`AGORA = "2026-10-21T12:00:00Z"`, fixture `con` com migrações):
  - `test_zero_interacao_nao_passa`; `test_uma_resposta_passa` (`email_respondido` de 30 dias atrás para o endereço); `test_quatro_mensagens_nao_passam_e_cinco_passam`; `test_fora_da_janela_nao_conta` (resposta de 400 dias atrás, mensagens de 366 dias).
  - `test_remetente_com_nome_e_maiuscula`: `remetente="Fulano <Fulano@X.COM>"` conta para `endereco="fulano@x.com"`.
  - `test_exclui_noreply_lista_e_notificacao`: `noreply@`, `no-reply@`, `donotreply@`, mensagens com `lista` preenchida não contam, mesmo em 10 mensagens.
  - `test_telefone_conta_escuta_msg_e_resposta_e_zero`: 5 mensagens de `escuta_msg` passam, 4 não; `respostas == 0`.
  Em `tests/escuta/test_contatos_propostas.py`:
  - `test_criar_so_com_interacao_suficiente`: remetente aprovado sem interação → nenhuma proposta e `abaixo_do_piso == 1`; com 5 mensagens em `escuta_msg` nos últimos 12 meses → 1 proposta `criar`. Atualizar os testes existentes de `criar` para semear a interação (helper `_interacao(con, numero, n=5)`).
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/escuta/test_interacao.py tests/escuta/test_contatos_propostas.py -q` → FAIL.
- [ ] **Step 3: Implementar** `interacao.py` (extrai o endereço com a regex já usada para `remetente`; usa a janela `[agora − 365 dias, agora]`; descarta `lista` não vazia e endereços que casam `noreply|no-reply|donotreply|mailer-daemon|notifica|newsletter`). No ramo `criar` de `gerar`, chamar `passa_piso(interacao(con, agora, telefone=numero))`; abaixo → `abaixo_do_piso += 1` e `continue`. Docstring de `gerar` atualizada. Constantes nomeadas no topo do módulo.
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS; `pytest tests/escuta -q` verde.
- [ ] **Step 5: Commit** — `git commit -m "feat(contatos): piso de interação (12 meses, 1 resposta ou 5 mensagens) para criar"`.

---

### Task 6: Aprovação em lote e painel

**Files:**
- Modify: `gabi/escuta/contatos_propostas.py` (`aprovar_correcoes`), `gabi/rotas/escuta.py` (docstrings de `listar_propostas`/`aprovar_correcoes_propostas`), `painel/src/telas/ContatosPropostas.tsx`
- Test: `tests/escuta/test_contatos_propostas.py`, teste da rota de propostas em `tests/` (achar com `grep -rl "aprovar-correcoes" tests`), `docs/api.md` se o texto do endpoint estiver lá

**Interfaces:**
- Consumes: tipo `adicionar_email` (Task 1) e campo `email_depois` devolvido por `cp.listar` (já é `select *`).
- Produces: `aprovar_correcoes` aprova também `tipo='adicionar_email'`; o painel mostra "Adicionar e-mail" e os e-mails, e o lote o inclui.

- [ ] **Step 1: Testes que falham:**
  - `test_aprovar_correcoes_aceita_adicionar_email_e_nao_criar_nem_apagar`: insere pendentes `adicionar_email`, `corrigir`, `criar`, `apagar_contato`; `aprovar_correcoes` com todos os ids devolve 2 e só `adicionar_email` e `corrigir` ficam `aprovada`.
  - Teste da rota: `POST /contatos/propostas/aprovar-correcoes` com ids de `adicionar_email` aprova; `GET /contatos/propostas` devolve `email_depois`.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/escuta/test_contatos_propostas.py <teste da rota> -q` → FAIL.
- [ ] **Step 3: Implementar.** `aprovar_correcoes`: `tipo in ('corrigir','corrigir_nome','adicionar_email')` (docstring: "apagar e criar só um a um"). `ContatosPropostas.tsx`: `Tipo` ganha `"adicionar_email"`, `ROTULOS["adicionar_email"] = "Adicionar e-mail"`, `EM_LOTE` inclui o tipo, `Proposta` ganha `email_depois: string | null`; na linha da proposta mostrar `email_depois` (separado por `, `) no lugar do "depois" de telefone para esse tipo; `rotulo()` continua sem nome nem telefone nem e-mail. Atualizar docstrings da rota. Rodar `npm run build` no painel (`painel/`) e conferir sem erros de tipo.
- [ ] **Step 4: Rodar e ver passar** — testes acima PASS; `npm run build` sem erro.
- [ ] **Step 5: Commit** — `git commit -m "feat(contatos): aprovar adicionar_email em lote e mostrar no painel"`.

---

### Task 7: ADR-022, documentação e verificação final

**Files:**
- Create: `docs/adr/022-enriquecer-contatos-email.md`
- Modify: `docs/api.md` e `docs/openapi.json` (regerar com `tools.gerar_docs_api` se o repo o exigir; ver `docs/runbook.md`), `docs/STATUS.md` (uma linha)

- [ ] **Step 1: Escrever a ADR-022** no molde da ADR-021 (Data, Estado "aceito (código na branch; instalar é passo do dono)", Spec, Plano, Estende ADR-020/021; Contexto; Decisões e razões numeradas; Consequências; Fora do escopo), cobrindo: tipo `adicionar_email`, filtros de geração (telefone único, nome compatível, só acrescenta), ponte sem DELETE, lote só para `adicionar_email`, piso de interação e sua limitação (WhatsApp sem resposta; histórico só acumula).
- [ ] **Step 2: Regerar docs da API** se o texto dos endpoints mudou (comando do runbook) e conferir `git diff --stat`.
- [ ] **Step 3: Suíte completa em shards** — mesmo script de `PROGRESSO-GOAL.md` (`suite_paralela.sh`); ler o **resumo do pytest** de cada shard (não só o exit code). Esperado: 0 falhas, incluindo `tests/cobrar/test_nibo.py`.
- [ ] **Step 4: Commit** — `git add docs && git commit -m "docs(contatos): ADR-022 enriquecer contatos com e-mail e piso de interação"`.
- [ ] **Step 5: Parar.** Merge na main, `npm run build` e `sudo ~/instalar-brain.sh` só quando o Ricardo mandar; depois conferir a migração 0074 e a linha `propostas:` do journal.
