# Limpeza de contatos da ness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Gabi passa a propor (com aprovação individual no painel) renomear contato com lixo no nome, apagar telefone inválido e apagar contato de nome de 1 caractere; e deixa de tratar número estrangeiro como inválido.

**Architecture:** Mesma fila `contato_proposta`, mesmo interruptor `contatos.escrita`, mesmo aplicador (`contatos_gravar.py`) e mesma ponte do Graph (`graph_ness_contatos.py`). Três tipos novos (`corrigir_nome`, `apagar_telefone`, `apagar_contato`), geração sem modelo, revalidação estrita antes de escrever.

**Tech Stack:** Python 3 (FastAPI, sqlite), pytest, painel React/vitest. Testes: `~/gabi-brain/.venv/bin/python -m pytest -q -p no:cacheprovider <arquivo>`; painel: `cd painel && npx vitest run tests/ContatosPropostas.test.tsx`.

**Spec:** `docs/superpowers/specs/2026-10-21-contatos-limpeza-design.md` (base: `2026-10-20-contatos-escrita-graph-design.md`, ADR-020).

## Global Constraints
- Nada vai ao Graph sem estado `aprovada` e sem `contatos.escrita` = `"ligado"` (nasce desligado; hoje está LIGADO em produção, ver Task 7).
- `apagar_telefone` e `apagar_contato` **nunca** entram em lote; o lote só aprova `corrigir` e `corrigir_nome`.
- Dado de terceiros (nome, telefone) nunca vai a log, exceção ou motivo; só contagens e motivos fixos (`contato_alterado`, `ja_existe`, `graph_indisponivel`).
- Limpeza de nome: só lixo (símbolos soltos, sobrescritos colados, espaços); NÃO mexe em caixa alta, NÃO completa nomes, NÃO altera `EMR3` (dígito ASCII), preserva parênteses, hífen, ponto e apóstrofo dentro do nome.
- Nome limpo de `corrigir_nome` precisa ter ≥ 2 caracteres; nome limpo de exatamente 1 caractere gera `apagar_contato` (e não `corrigir_nome`).
- Estrangeiro válido = `+<DDI≠55>` com 8 a 15 dígitos no total, nunca convertido para +55.
- Código novo segue o estilo do arquivo vizinho (docstrings em pt-BR curtas, `# noqa: BLE001` nos `except Exception` de fronteira).
- Não dar push nem instalar em produção sem pedido do Ricardo.

## Review Focus
- Contato com **dois contatos de mesmo nome sujo** (o "José Rodrigo Carvalho⁹" aparece em 2 telefones): uma proposta por `graph_id`, nunca duas para o mesmo contato.
- Contato "U" que **tem e-mail ou 2º telefone**: não vira `apagar_contato` (gerador) e a ponte devolve `alterado` se isso mudar antes de gravar.
- `apagar_telefone` em contato com **2 telefones home**: remove só o número da proposta, mantém o outro.
- Proposta **recusada** não é regerada na sincronização seguinte (índice único + `_ja_decidida` com os tipos novos).
- Contato **editado no Outlook** entre a proposta e a gravação: `contato_alterado`, nada escrito.

---

### Task 1: Migração 0073 (tipos e origens novos)

**Files:**
- Create: `migrations/0073_contato_proposta_limpeza.sql`
- Test: `tests/escuta/test_contatos_propostas.py`

**Interfaces:**
- Produces: `contato_proposta.tipo` aceita `'criar','corrigir','corrigir_nome','apagar_telefone','apagar_contato'`; `origem` aceita `'whatsapp','telefone_invalido','nome_sujo','nome_curto'`. Linhas e índice `contato_proposta_aberta` preservados. SQLite não altera `check`: recriar a tabela.

- [ ] **Step 1: Write the failing test** `test_migracao_0073_aceita_tipos_novos_e_preserva_linhas` em `tests/escuta/test_contatos_propostas.py`: insere uma linha `criar` e uma `corrigir` antes (use a fixture/`migrar` com `ate=72` se o helper existir; senão insere após migrar tudo e confira só os `check`), roda a migração, assert que as linhas continuam, que `insert` de `tipo='apagar_contato', origem='nome_curto'` passa, que `tipo='qualquer'` levanta `sqlite3.IntegrityError`, e que o índice `contato_proposta_aberta` existe (`select name from sqlite_master where name='contato_proposta_aberta'`).
- [ ] **Step 2: Run test to verify it fails** — `pytest tests/escuta/test_contatos_propostas.py::test_migracao_0073_aceita_tipos_novos_e_preserva_linhas -q`; Expected: FAIL (IntegrityError no tipo novo).
- [ ] **Step 3: Write `migrations/0073_contato_proposta_limpeza.sql`**: `create table contato_proposta_nova` com as mesmas colunas da 0072 e os `check` ampliados; `insert ... select` de todas as colunas; `drop table contato_proposta`; `alter table ... rename`; recriar `contato_proposta_aberta` (mesma definição da 0072). Sem `begin/commit` próprios se o runner já transaciona (conferir como a 0071 faz).
- [ ] **Step 4: Run test to verify it passes** — mesmo comando; Expected: PASS. Rode também `pytest tests/escuta/test_contatos_propostas.py tests/escuta/test_contatos_gravar.py -q` (nada quebrou).
- [ ] **Step 5: Commit** — `git add migrations/0073_contato_proposta_limpeza.sql tests/escuta/test_contatos_propostas.py && git commit -m "feat(contatos): migração 0073 com tipos de limpeza"`.

### Task 2: Número estrangeiro deixa de ser inválido

**Files:**
- Modify: `gabi/escuta/contatos.py` (`_telefone`, linhas ~57-76)
- Test: `tests/escuta/test_contatos.py`

**Interfaces:**
- Produces: `_telefone(item) -> str | None` devolve E.164 `+<dígitos>` para número com `+`/`00` e DDI ≠ 55 quando o total de dígitos está em 8..15 e não há ramal (`_RAMAL`); ramal e curtos continuam `None`; +55 segue por `normalizar_telefone` (inalterado).

- [ ] **Step 1: Write the failing tests** em `tests/escuta/test_contatos.py`: `test_telefone_estrangeiro_valido` (`{"telefone": "+1 (415) 555-2671"}` → `"+14155552671"`; `{"telefone": "+44 20 7946 0958"}` → `"+442079460958"`; `"0044 20 7946 0958"` → `"+442079460958"`), `test_telefone_estrangeiro_invalido` (`"+1 415"` → None, `"+1 415 555 2671 ramal 12"` → None, 16 dígitos → None), `test_sincronizar_estrangeiro_nao_conta_invalido` (um item com `+1 415 555 2671` entra em `contato_google` e `invalidos == 0`), `test_telefone_brasil_inalterado` (casos existentes continuam).
- [ ] **Step 2: Run** — `pytest tests/escuta/test_contatos.py -q`; Expected: os novos FAIL.
- [ ] **Step 3: Implement** no ramo `if t.startswith("+") and not ...startswith("55")` de `_telefone`: em vez de `return None`, devolver `"+" + dígitos` se `8 <= len(dígitos) <= 15`, senão None (o teste de ramal já retorna antes).
- [ ] **Step 4: Run** — `pytest tests/escuta -q -k contatos`; Expected: PASS, nenhum teste antigo quebrado.
- [ ] **Step 5: Commit** — `git commit -am "feat(contatos): aceita telefone estrangeiro como válido"`.

### Task 3: Ponte do Graph (renomear, apagar telefone, apagar contato)

**Files:**
- Modify: `gabi/fontes/graph_ness_contatos.py` (docstring do módulo: já não é "sem apagar", ver ADR-021), `gabi/fontes/graph_ness.py` (wrappers junto de `contato_corrigir`), `gabi/fontes/ponte.py` (allowlist linha ~30 e cliente junto de `contato_corrigir` ~234)
- Test: `tests/fontes/test_graph_ness_contatos_escrita.py`, `tests/fontes/test_ponte.py`

**Interfaces:**
- Produces em `graph_ness_contatos`: `renomear(gr, conta, graph_id, nome_antes: str, nome_depois: str) -> {"resultado": "ok"|"alterado"}`; `apagar_telefone(gr, conta, graph_id, campo: str, telefone_antes: str) -> {"resultado": "ok"|"alterado"}`; `apagar(gr, conta, graph_id, nome_antes: str) -> {"resultado": "ok"|"alterado"}`. Wrappers em `GraphNess` e métodos no cliente da ponte com os mesmos nomes prefixados `contato_` (`contato_renomear`, `contato_apagar_telefone`, `contato_apagar`), validando `resultado in ("ok","alterado")` como `contato_corrigir`.
- Consumes: `_escrever(gr, metodo, url, corpo)` (aceitar `DELETE` sem corpo: `corpo=None` → não envia JSON), `_base`, `_texto`, `_ID_CONTATO`, `gr._get`.
- Regras: `renomear` lê `?$select=displayName`, confere `displayName == nome_antes`, PATCH só `{"displayName": nome_depois}`. `apagar_telefone`: `campo` em `mobile|home|business` (senão `ErroGraphNess`); lê `mobilePhone,homePhones,businessPhones`; mobile confere `mobilePhone == telefone_antes` e PATCH `{"mobilePhone": null}`; home/business confere que `telefone_antes` está na lista e PATCH `{"homePhones"|"businessPhones": lista sem ele}`. `apagar`: lê `displayName,mobilePhone,homePhones,businessPhones,emailAddresses`; confere nome, `emailAddresses` vazio e total de telefones ≤ 1, senão `alterado`; `DELETE`. Nenhum erro carrega corpo, nome ou telefone.

- [ ] **Step 1: Write failing tests** em `tests/fontes/test_graph_ness_contatos_escrita.py` (mesmo estilo de fake HTTP dos testes de `corrigir`): `test_renomear_ok` (GET devolve nome igual → 1 PATCH com corpo exatamente `{"displayName": "..."}`), `test_renomear_alterado_nao_escreve` (nome diferente → `{"resultado":"alterado"}`, zero PATCH), `test_apagar_telefone_mobile_ok`, `test_apagar_telefone_home_preserva_outro` (lista `[a, b]` apaga `a` → PATCH `{"homePhones": [b]}`), `test_apagar_telefone_alterado`, `test_apagar_telefone_campo_invalido`, `test_apagar_ok` (DELETE feito), `test_apagar_recusa_com_email` e `test_apagar_recusa_com_dois_telefones` (→ `alterado`, zero DELETE), `test_apagar_erro_nao_vaza_corpo` (HTTP 500 → `ErroGraphNess` cuja mensagem não contém nome nem número). Em `tests/fontes/test_ponte.py`: `test_ponte_permite_os_tres_metodos_novos` e `test_cliente_valida_resposta` (resultado inválido → `ErroGraphNess`).
- [ ] **Step 2: Run** — `pytest tests/fontes/test_graph_ness_contatos_escrita.py tests/fontes/test_ponte.py -q`; Expected: FAIL.
- [ ] **Step 3: Implement** os três em `graph_ness_contatos.py` (reusar `_escrever`; ajustar para `corpo` opcional), wrappers em `graph_ness.py` com import local como `contato_corrigir`, allowlist + cliente em `ponte.py`.
- [ ] **Step 4: Run** — mesmos arquivos + `pytest tests/fontes -q`; Expected: PASS (inclui a varredura de leitura de `graph_ness.py`, que não pode quebrar).
- [ ] **Step 5: Commit** — `git commit -am "feat(contatos): ponte renomear/apagar telefone/apagar contato"`.

### Task 4: Gerador das propostas novas

**Files:**
- Modify: `gabi/escuta/contatos_propostas.py` (`gerar`, `_ja_decidida`, novas `limpar_nome`), `gabi/escuta/contatos.py:218` (a linha de contagens imprime também os tipos novos)
- Test: `tests/escuta/test_contatos_propostas.py`

**Interfaces:**
- Produces: `limpar_nome(nome: str) -> str`; `gerar(con, agora) -> {"criar","corrigir","corrigir_nome","apagar_telefone","apagar_contato"}` (inteiros). Propostas novas gravadas assim: `corrigir_nome`: `graph_id`, `nome_antes`, `nome_depois`=limpo, `telefone_antes=null`, `telefone_depois=''`, `origem='nome_sujo'`. `apagar_telefone`: `graph_id`, `nome_antes`=nome, `telefone_antes`=`telefone_original`, `nome_depois`=nome, `telefone_depois=''`, `origem='telefone_invalido'` (o `campo` não é guardado na proposta: a Task 5 o lê de `contato_graph.campo`). `apagar_contato`: `graph_id`, `nome_antes`=nome, `telefone_antes`=telefone do contato, `nome_depois`=nome limpo (1 caractere, porque a coluna é `not null`), `telefone_depois=''`, `origem='nome_curto'`.
- `limpar_nome`: remove caracteres Unicode de categoria `S*`/`P*` que estejam soltos (isolados por espaço ou nas pontas, ex. `|`), troca sobrescritos/subscritos Unicode (`⁹`, `₃`) colados no fim de palavra por nada, colapsa espaços, `strip`. Preserva `()`, `-`, `.`, `'`, `&` dentro do texto e dígitos ASCII (`EMR3`, `Haras itaparica`).
- Regras de `gerar`: por `graph_id` distinto de `contato_graph` com nome não vazio: `limpo = limpar_nome(nome)`; `len(limpo) == 1` → `apagar_contato` **se** o contato tem exatamente 1 linha em `contato_graph` e nenhum e-mail em `contato_google_email` com esse telefone; senão se `limpo != nome` e `len(limpo) >= 2` → `corrigir_nome` (uma por `graph_id`, mesmo que o contato tenha vários telefones). `apagar_telefone`: linhas de `contato_graph` com `telefone is null` (e `telefone_original` não vazio) → uma por `(graph_id, telefone_original)`. `_ja_decidida` e o `insert` passam a servir os 3 tipos (a chave é a mesma: conta, tipo, graph_id, telefone_depois, nome_depois).

- [ ] **Step 1: Write failing tests**: `test_limpar_nome` (parametrizado: `"José Rodrigo Carvalho⁹"→"José Rodrigo Carvalho"`, `"Jaqueline Jurkovich |"→"Jaqueline Jurkovich"`, `"EMR3 Segurança"` inalterado, `"Antonio Américo (Tonico) Barbosa De Oliveira"` inalterado, `"Gabriela Andrade - HomeCred"` inalterado, `"NOFARO"` inalterado, `"  Ana   Lima "→"Ana Lima"`), `test_gera_corrigir_nome_uma_por_contato` (contato com 2 telefones e nome sujo → 1 proposta), `test_nao_gera_nome_para_caixa_alta_nem_emr3`, `test_gera_apagar_contato_nome_de_uma_letra`, `test_nao_apaga_contato_u_com_email_ou_segundo_telefone`, `test_gera_apagar_telefone_para_invalido`, `test_gerar_idempotente_e_respeita_recusada` (rodar `gerar` 2x = mesmas linhas; recusar e rodar de novo não recria), `test_gerar_retorna_todas_as_contagens`.
- [ ] **Step 2: Run** — `pytest tests/escuta/test_contatos_propostas.py -q`; Expected: FAIL.
- [ ] **Step 3: Implement** `limpar_nome` e a extensão de `gerar` como na interface; ajustar a linha de impressão em `contatos.py` para `propostas: criar=.. corrigir=.. nomes=.. apagar_telefone=.. apagar_contato=..` (só contagens).
- [ ] **Step 4: Run** — `pytest tests/escuta -q`; Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(contatos): gerador de limpeza de nome, telefone inválido e contato de uma letra"`.

### Task 5: Aplicar as propostas novas

**Files:**
- Modify: `gabi/escuta/contatos_gravar.py` (`_aplicar` despacho + 3 funções)
- Test: `tests/escuta/test_contatos_gravar.py`

**Interfaces:**
- Consumes: `graph.contato_renomear(conta, graph_id, nome_antes, nome_depois)`, `graph.contato_apagar_telefone(conta, graph_id, campo, telefone_antes)`, `graph.contato_apagar(conta, graph_id, nome_antes)` (Task 3), retornando `{"resultado": "ok"|"alterado"}`.
- Produces: `_aplicar_corrigir_nome(con, graph, p, agora)`, `_aplicar_apagar_telefone(...)`, `_aplicar_apagar_contato(...)`, cada uma `-> str | None` (motivo ou None), no padrão de `_aplicar_corrigir`. Despacho em `_aplicar` por `p["tipo"]` (dict de tipo → função; tipo desconhecido → `contato_alterado`).
- Regras: revalidação local antes do Graph: a linha de `contato_graph` (`conta`, `graph_id`, e `nome` igual a `nome_antes` / `telefone_original` igual a `telefone_antes`) ainda existe e a conta segue em `escuta.contas_contatos`, senão `CONTATO_ALTERADO`. `corrigir_nome`: depois do `ok`, `update contato_graph set nome=?` para todas as linhas do `graph_id` + `aplicada`. `apagar_telefone`: `campo` lido de `contato_graph.campo` (nulo → `CONTATO_ALTERADO`); após `ok`, `delete` da linha de `contato_graph` + remove o telefone de `contato_google` se for de uma só linha; `aplicada`. `apagar_contato`: depois do `ok`, `delete from contato_graph where conta=? and graph_id=?` + `delete from contato_google where conta=? and telefone=?` + `aplicada`. Resultado `alterado` → `CONTATO_ALTERADO`; exceção/resultado inválido → `GRAPH_INDISPONIVEL`. Tudo local na mesma transação via `_registrar`.

- [ ] **Step 1: Write failing tests** (mesmo fake de graph dos testes de `_aplicar_corrigir`): para cada tipo: `..._ok_grava_e_marca_aplicada` (chamada ao fake com os argumentos exatos, `contato_graph` atualizado, estado `aplicada`), `..._contato_mudou_localmente_nao_chama_graph` (`contato_alterado`, zero chamadas), `..._graph_devolve_alterado`, `..._graph_indisponivel` (exceção → `graph_indisponivel`, estado `falhou`), `..._desligado_so_simula` (zero chamadas, estado intacto, `simuladas` conta); mais `test_apagar_telefone_sem_campo_e_alterado` e `test_tipo_desconhecido_vira_contato_alterado`.
- [ ] **Step 2: Run** — `pytest tests/escuta/test_contatos_gravar.py -q`; Expected: FAIL.
- [ ] **Step 3: Implement** as três funções e o despacho.
- [ ] **Step 4: Run** — `pytest tests/escuta -q`; Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(contatos): aplicar renomear, apagar telefone e apagar contato"`.

### Task 6: Rotas e painel

**Files:**
- Modify: `gabi/escuta/contatos_propostas.py` (`aprovar_correcoes`: `tipo in ('corrigir','corrigir_nome')`), `gabi/rotas/escuta.py` (docstrings; nada mais se `listar` já devolve todos os tipos), `painel/src/telas/ContatosPropostas.tsx`
- Test: `tests/rotas/test_escuta.py`, `tests/escuta/test_contatos_propostas.py`, `painel/tests/ContatosPropostas.test.tsx`

**Interfaces:**
- Produces no painel: `Proposta.tipo` ganha `"corrigir_nome" | "apagar_telefone" | "apagar_contato"` e `origem` ganha `"nome_sujo" | "nome_curto"`. Rótulos: "Corrigir nome", "Apagar telefone", "Apagar contato"; linha mostra antes → depois (apagar telefone: `nome telefone_antes → (telefone removido)`; apagar contato: `nome telefone → (contato apagado)`). O botão em lote ("Aprovar todas as correções") passa só os ids de `corrigir` e `corrigir_nome`; apagar_* têm botão **Aprovar** individual com `window.confirm`-equivalente do painel (use o padrão de confirmação já existente nas telas; se não houver, `aria-label` distinto e um segundo clique "Confirmar apagar").

- [ ] **Step 1: Write failing tests**: backend `test_aprovar_correcoes_inclui_corrigir_nome` e `test_aprovar_correcoes_ignora_apagar_telefone_e_apagar_contato` (ids de apagar_* passados explicitamente continuam `pendente`); rota `test_listar_devolve_tipos_novos`; painel `mostra rótulos dos tipos novos`, `lote não envia ids de apagar_telefone nem apagar_contato` (mock de `api.post` confere o corpo `{ids}`), `apagar contato exige confirmação antes de aprovar`, e o aria-label de cada botão não contém nome nem telefone.
- [ ] **Step 2: Run** — backend `pytest tests/rotas/test_escuta.py tests/escuta/test_contatos_propostas.py -q`; painel `cd painel && npx vitest run tests/ContatosPropostas.test.tsx`; Expected: FAIL.
- [ ] **Step 3: Implement** a mudança em `aprovar_correcoes` e a tela.
- [ ] **Step 4: Run** — os mesmos comandos + `npm run build` em `painel/` (gera `gabi/painel/assets`); Expected: PASS e build ok.
- [ ] **Step 5: Commit** — `git add -A gabi painel tests && git commit -m "feat(contatos): painel e lote para a limpeza"` (confira com `git status` que só entrou código deste plano).

### Task 7: ADR-021, docs e verificação final

**Files:**
- Create: `docs/adr/021-limpeza-contatos-graph.md`
- Modify: `docs/STATUS.md`, `docs/runbook.md` (seção `#contatos-escrita`), `docs/adr/020-escrita-contatos-graph.md` (uma linha: "estendida pela ADR-021"), `docs/api.md` (regerar com o gerador do projeto, `tools.gerar_docs_api`)

**Interfaces:**
- ADR-021 registra: a exceção ao "sem apagar" da ADR-020, os três tipos, a regra de nome (só lixo), o tratamento do estrangeiro, "apagar nunca em lote", revalidação estrita e a irreversibilidade no Graph da ness. Runbook ganha: como conferir a fila nova, e que `contatos.escrita` **está ligado** em produção (ligado em 21/10): as propostas novas aprovadas serão gravadas na rodada seguinte do timer (10:00) ou no `systemctl start gabi-brain-contatos`, então aprovar já é decidir gravar.

- [ ] **Step 1: Write ADR-021 e atualizar STATUS/runbook/ADR-020; regerar `docs/api.md`** (`~/gabi-brain/.venv/bin/python -m tools.gerar_docs_api`, conferir que o diff só mostra o que mudou).
- [ ] **Step 2: Rodar a suíte completa em shards** com o script `scratchpad/suite_paralela.sh 5` (resumo em `/tmp/claude-1001/`); Expected: 0 failed em todos os shards; ler o resumo do pytest (não confiar só no exit code). Rodar também `cd painel && npx vitest run`; Expected: tudo verde.
- [ ] **Step 3: Commit** — `git add docs && git commit -m "docs: ADR-021 e runbook da limpeza de contatos"`.
- [ ] **Step 4: Parar.** Instalar (`sudo ~/instalar-brain.sh`, que precisa do build do painel e aplica a migração 0073) e a sincronização são passos do Ricardo, só quando ele pedir. Depois de instalar e sincronizar, conferir só contagens com `sudo journalctl -u gabi-brain-contatos -n 20`.
