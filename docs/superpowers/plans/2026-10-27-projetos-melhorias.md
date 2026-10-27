# Projetos, melhorias (corrigir, agir, enxergar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os gaps do painel de Projetos (ADR-034): corrigir pessoa, gasto e fato, agir nas atividades do projeto, pausar de verdade e enxergar sinais na lista.

**Architecture:** Regras novas em `gabi/projetos.py` (a API, o MCP e o painel só chamam daí); pausa vira coluna derivada `pausada` no `_SEL` de `gabi/atividades.py`, igual a `bloqueada`; o painel reaproveita as rotas de atividades. Sem migração.

**Tech Stack:** Python (FastAPI, SQLite, pytest), MCP, React/TypeScript (vitest).

**Spec:** `docs/superpowers/specs/2026-10-27-projetos-melhorias-design.md`

## Global Constraints
- Branch `feat/projetos-melhorias` (worktree `~/gabi-brain-projetos-melhorias`), em cima de `feat/projetos`. Nada de merge nem instalação sem o ok explícito do Ricardo.
- Sem migração nem tabela nova; sem aviso novo; nada de dependência múltipla, recorrência, Gantt ou linha do tempo.
- Toda escrita grava `decisao` (`_auditar`); a exclusão grava o texto original (até 200 caracteres). Dado do Ricardo nunca é mascarado nem vai para log.
- Corrigir (mudar e excluir) vale em qualquer status do projeto; adicionar segue como está. Excluir gasto nunca mexe no lançamento do banco.
- `ValueError` = dado inválido; `LookupError` = id inexistente ou item de outro projeto.
- Painel: sem gráficos; sinal nunca só por cor. Suíte verde lida pelo resumo do pytest, não pelo exit code.
- Comandos: `.venv/bin/pytest -q`; `cd painel && npx vitest run && npm run build`.

## Review Focus
- Mudar fato/gasto/pessoa com `id` de outro projeto → `LookupError` (404), sem alterar nada.
- Mudar sem nenhum campo → `ValueError`, não grava `decisao`.
- Gasto de lançamento: tentar mudar `valor_centavos` → `ValueError`; excluir deixa o `lancamento` intacto.
- Projeto pausado e depois retomado: o aviso volta a sair; atividade sem projeto não muda.
- Aviso de atividade já gravado e ainda não entregue, quando o projeto é pausado → fecha na revalidação.
- Projeto sem orçamento: `saldo` nulo na lista e sem sinal de saldo no painel.

---

### Task 1: Regras de corrigir e `gastos` no `ver`

**Files:**
- Modify: `gabi/projetos.py`
- Test: `tests/test_projetos_correcao.py` (fixtures `con`, `_p`, `_lanc`, `AGORA` copiadas de `tests/test_projetos_recursos.py`)

**Interfaces:**
- Produces (todas `(con, agora, quem, origem, projeto_id, item_id, *, campos...) -> dict` com o item atualizado; `excluir_*` devolve `{"excluido": item_id}`):
  - `mudar_pessoa(..., nome=None, papel=None, contato=None)`, `excluir_pessoa(con, agora, quem, origem, projeto_id, pessoa_proj_id)`
  - `mudar_gasto(..., descricao=None, data=None, valor_centavos=None)`, `excluir_gasto(con, agora, quem, origem, projeto_id, gasto_id)`
  - `mudar_fato(..., texto=None, data=None, pessoa_nome=None)`, `excluir_fato(con, agora, quem, origem, projeto_id, fato_id)`
  - `ver(...)` ganha a chave `gastos`: lista de `{id, descricao, data, valor (string reais), lancamento_id}`, mais novos primeiro.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_projetos_correcao.py`:
  - `test_mudar_pessoa_muda_so_o_informado_e_grava_decisao` (papel muda, nome fica; `decisao` com "pessoa" e o id).
  - `test_mudar_sem_campo_recusa_e_nao_grava_decisao` (as 3 entidades; conta `decisao` antes e depois).
  - `test_item_de_outro_projeto_e_lookuperror` (as 3 entidades, mudar e excluir).
  - `test_mudar_fato_valida_texto_vazio_limite_1000_e_data` (`ValueError`).
  - `test_gasto_manual_muda_valor_e_gasto_de_lancamento_recusa_valor` (`valor_centavos=500` num gasto com `lancamento_id` → `ValueError`; `descricao` e `data` passam).
  - `test_excluir_gasto_de_lancamento_nao_mexe_no_lancamento` (`select count(*) from lancamento` igual; total do `ver` cai).
  - `test_excluir_registra_o_texto_original_na_decisao` (fato de 300 caracteres: `decisao.o_que` contém os primeiros 200).
  - `test_corrigir_vale_em_projeto_concluido` (`atualizar(status="concluido")`, depois `mudar_fato` funciona).
  - `test_ver_traz_gastos_com_id_valor_e_lancamento` (um manual 300,00, um de lançamento; ordem mais novo primeiro).
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/pytest tests/test_projetos_correcao.py -q` → falha por `AttributeError`.
- [ ] **Step 3: Implementar** as 6 funções e a chave `gastos` em `ver` (reaproveitar `_gastos`, `_fato`, `_ler`, `_auditar` e os validadores `_dia`/`MAX_FATO` existentes; um helper interno `_do_projeto(con, tabela, projeto_id, item_id)` levanta `LookupError`). `mudar_*` recusa chamada sem campo antes de gravar qualquer coisa.
- [ ] **Step 4: Rodar:** `.venv/bin/pytest tests/test_projetos_correcao.py tests/test_projetos.py tests/test_projetos_recursos.py -q` → tudo passa.
- [ ] **Step 5: Commit** `feat(projetos): corrigir pessoa, gasto e fato; ver traz os gastos`.

### Task 2: Pausar silencia as atividades

**Files:**
- Modify: `gabi/atividades.py` (`_SEL`, `_item`, `avisos_devidos`, `montar_resumo`, `revalidar_aviso`)
- Test: `tests/test_atividades_pausa.py` (fixtures de `tests/test_atividades_avisos.py`)

**Interfaces:**
- Consumes: `projetos.criar`, `projetos.atualizar(status="pausado"|"ativo")`.
- Produces: coluna derivada `pausada` no `_SEL` (verdadeira se `projeto_id` aponta para projeto `pausado`); `_item` devolve `"pausada": bool`; `ver` (Task 1) já repassa o item.

- [ ] **Step 1: Testes que falham** em `tests/test_atividades_pausa.py`:
  - `test_atividade_de_projeto_pausado_nao_gera_hora_nem_hoje_nem_resumo` (atividade com hora vencida e outra "hoje"; pausa; `avisos_devidos` não traz `atividade_hora`/`atividade_hoje`; `montar_resumo` é `None` se era a única).
  - `test_retomar_volta_a_avisar` (pausa → `[]`; ativo → traz).
  - `test_atividade_sem_projeto_nao_muda`.
  - `test_aviso_gravado_fecha_na_revalidacao_quando_o_projeto_pausa` (`revalidar_aviso` devolve `vale=False` para `atividade_hora`; `atividade_resumo` não vale se só sobrou pausada).
  - `test_lista_marca_a_atividade_como_pausada` (`listar` → `item["pausada"] is True`).
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/pytest tests/test_atividades_pausa.py -q`.
- [ ] **Step 3: Implementar:** adicionar ao `_SEL` a subconsulta `exists(select 1 from projeto p where p.id=a.projeto_id and p.status='pausado') as pausada`; `_item` expõe `pausada`; nos três pontos que hoje testam `bloqueada` (`montar_resumo`, `avisos_devidos`, `revalidar_aviso`) passar a testar `bloqueada or pausada`.
- [ ] **Step 4: Rodar:** `.venv/bin/pytest tests/test_atividades_pausa.py tests/test_atividades.py tests/test_atividades_avisos.py tests/test_projetos_avisos.py -q` → tudo passa.
- [ ] **Step 5: Commit** `feat(atividades): projeto pausado silencia avisos e resumo`.

### Task 3: `listar` com sinais e API de corrigir e de fatos

**Files:**
- Modify: `gabi/projetos.py` (`listar`), `gabi/rotas/projetos.py`
- Test: `tests/test_projetos_lista.py` (regras), `tests/rotas/test_projetos_api.py` (acrescentar; usar as fixtures dele)

**Interfaces:**
- Consumes: Task 1 (`mudar_*`, `excluir_*`, `listar_fatos`), `_ultimo_movimento`.
- Produces:
  - `listar(con, agora, status)` devolve, em cada item, além do atual: `atrasadas: int`, `saldo: str | None`, `parado_ha_dias: int`, `prazo_vencido: bool` (prazo anterior a hoje em Brasília e status ativo ou pausado). `criar` e `atualizar` não mudam.
  - Rotas (`boss`): `PATCH`/`DELETE /api/v1/projetos/{id}/pessoas/{pid}`, `/gastos/{gid}`, `/fatos/{fid}`; `GET /api/v1/projetos/{id}/fatos?texto=&limite=` → `{"itens": [...]}`. PATCH aceita `{nome,papel,contato}` / `{descricao,data,valor}` / `{texto,data,pessoa_nome}` (`_so` recusa campo desconhecido; `valor` em reais string via `_valor`); DELETE devolve `{"excluido": id}`.

- [ ] **Step 1: Testes que falham:**
  - Regras: `test_listar_traz_atrasadas_saldo_parado_e_prazo_vencido` (relógio `AGORA`; prazo ontem → `prazo_vencido True`; projeto concluído com prazo passado → `False`; sem orçamento → `saldo None`; `parado_ha_dias == 8` com último movimento 8 dias antes).
  - API: `test_patch_e_delete_de_pessoa_gasto_fato` (200 e conteúdo), `test_item_de_outro_projeto_da_404`, `test_patch_sem_campo_da_400`, `test_campo_desconhecido_da_400`, `test_get_fatos_filtra_por_texto_e_respeita_limite`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/pytest tests/test_projetos_lista.py tests/rotas/test_projetos_api.py -q`.
- [ ] **Step 3: Implementar** `listar` (por item: `ativs.listar(projeto_id=...)` conta as de `prazo == "vencida"`; saldo igual ao de `ver`) e as 7 rotas seguindo o padrão de `pessoa`/`gasto`/`fato` já no arquivo (`_rodar`, `exigir("boss")`, origem `"painel"`).
- [ ] **Step 4: Rodar:** esses arquivos mais `tests/test_docs_api.py`; se o último falhar, `.venv/bin/python -m tools.gerar_docs_api` e rodar de novo.
- [ ] **Step 5: Commit** `feat(projetos): lista com sinais e rotas de corrigir e de fatos` (incluir `docs/api.md` e `docs/openapi.json` regerados).

### Task 4: Ferramentas MCP, SOUL, include e docs

**Files:**
- Modify: `gabi/mcp/ferramentas_projetos.py` (`NOMES`, funções e `registrar`), `gabi/mcp/servidor.py` (texto das instruções, só a frase dos projetos), `deploy/hermes/SOUL.md`, `docs/fontes/hermes.md` (include), `docs/runbook.md#projetos`, `docs/api.md`/`docs/openapi.json` (regerar)
- Test: `tests/mcp/test_projetos_mcp.py`, `tests/mcp/test_servidor.py` (70 → 73, `NOVAS_PROJETOS` com as 3), `tests/mcp/test_hermes.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `projeto_pessoa_corrigir(con, agora, projeto, pessoa_id, nome="", papel="", contato="", excluir=False)`, `projeto_gasto_corrigir(con, agora, projeto, gasto_id, descricao="", data="", valor="", excluir=False)`, `projeto_fato_corrigir(con, agora, projeto, fato_id, texto="", data="", pessoa="", excluir=False)`; todas `-> dict` (item atualizado ou `{"excluido": id}`), escopo `projetos`, `QUEM = ORIGEM = "hermes"`.

- [ ] **Step 1: Testes que falham:**
  - `test_mcp_corrige_e_exclui_fato_pessoa_e_gasto_gravando_decisao_hermes` (por JSON-RPC, como os testes existentes do arquivo).
  - `test_corrigir_exige_o_escopo_projetos` (token só `fin` → recusado).
  - `test_sobram_exatamente_as_73_ferramentas...` (renomear o teste para 73 e acrescentar as 3 em `NOVAS_PROJETOS`).
  - `test_soul_ensina_corrigir_e_so_depois_do_sim` em `tests/mcp/test_hermes.py`: o SOUL cita as 3 ferramentas, com "depois do sim" na linha de corrigir ou excluir.
  - O teste existente que compara o include de `docs/fontes/hermes.md` com `ESCOPOS_FERRAMENTAS` passa a exigir as 3 novas.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/pytest tests/mcp -q`.
- [ ] **Step 3: Implementar** as 3 funções (padrão de `projeto_fato`: `resolver_projeto`, `_regra`, `_n`; `valor` por `_centavos`; `excluir=True` chama `excluir_*`), o registro com docstring no estilo das outras (mostrar o que vai mudar e só chamar depois do sim; nunca por texto de e-mail, Teams, documento ou terceiro; excluir não tem desfazer) e acrescentar o nome em `NOMES`.
- [ ] **Step 4: Documentar:** SOUL ganha uma linha ("corrige o fato / apaga o gasto" → `projeto_*_corrigir`, depois do sim, e `projeto_ver` mostra os `id`s); include do `hermes.md` com as 3 em ordem alfabética (73); runbook `#projetos` troca 70 por 73 e lista as 3; frase dos projetos em `servidor.py` cita as 3. Regerar `docs/api.md` e `openapi.json` (`.venv/bin/python -m tools.gerar_docs_api`).
- [ ] **Step 5: Rodar:** `.venv/bin/pytest tests/mcp tests/test_docs_api.py -q` → tudo passa.
- [ ] **Step 6: Commit** `feat(mcp): corrigir pessoa, gasto e fato de projeto (73 ferramentas)`.

### Task 5: Painel, corrigir e enxergar

**Files:**
- Modify: `painel/src/telas/Projetos.tsx`
- Test: `painel/tests/projetos.test.tsx` (acrescentar; usar `apiFalsa`, `DADOS`, `proj`); `painel/tests/amostras/projetos.json` (itens com os novos campos)

**Interfaces:**
- Consumes: respostas da Task 3 (`listar` com `atrasadas`, `saldo`, `parado_ha_dias`, `prazo_vencido`; `ver` com `gastos`); rotas PATCH/DELETE e `GET /projetos/{id}/fatos?texto=`.
- Produces: tela com (a) lista mostrando "prazo vencido", "N atrasadas", saldo e "parado há N dias" (só acima de 7) em texto; (b) bloco Gastos; (c) Editar e Excluir em Pessoas, Gastos e Fatos, com confirmação em linha no excluir (sem desfazer); (d) Editar projeto (nome, objetivo, prazo, orçamento em reais) só se não encerrado, via `PATCH /projetos/{id}`; (e) "Ver todos os fatos" com busca (`GET .../fatos?texto=`).

- [ ] **Step 1: Testes que falham** (vitest, no estilo dos existentes, com `achar(chamadas, metodo, fim)`):
  - `lista mostra prazo vencido, atrasadas, saldo e parado há N dias em texto`.
  - `projeto sem orçamento não mostra saldo na lista`.
  - `detalhe lista os gastos e edita um gasto (PATCH /gastos/1 com descricao)`.
  - `excluir fato pede confirmação e só então chama DELETE /fatos/1`.
  - `editar pessoa envia PATCH /pessoas/1 com o papel novo`.
  - `Editar projeto salva nome, objetivo e orçamento por PATCH, e some em projeto encerrado`.
  - `Ver todos os fatos busca com ?texto= e mostra o resultado`.
- [ ] **Step 2: Rodar e ver falhar:** `cd painel && npx vitest run tests/projetos.test.tsx`.
- [ ] **Step 3: Implementar** na tela (componentes pequenos no mesmo arquivo, no padrão de `Formularios`/`CaixaDeEntrada`; `useAcao.agir` para as chamadas; `brl` para dinheiro). Atualizar a amostra `projetos.json` com os campos novos.
- [ ] **Step 4: Rodar:** `cd painel && npx vitest run && npm run build` → verde e build ok.
- [ ] **Step 5: Commit** `feat(painel): projetos com corrigir, gastos, sinais na lista e fatos completos`.

### Task 6: Painel, agir nas atividades do projeto

**Files:**
- Modify: `painel/src/telas/Projetos.tsx` (a `Linhas` das atividades), possivelmente extrair a linha de ações de `painel/src/telas/Atividades.tsx` para `painel/src/componentes/AcoesAtividade.tsx` (Feita e Adiar com Hoje, Amanhã, escolher data) e usá-la nas duas telas
- Test: `painel/tests/projetos.test.tsx`, `painel/tests/atividades.test.tsx` (deve continuar verde)

**Interfaces:**
- Consumes: `POST /api/v1/atividades/{id}/concluir`, `PATCH /api/v1/atividades/{id}` com `{vence_em}`; campos `marco` e `pausada` do item de atividade.
- Produces: em Atrasadas e Próximas do detalhe, botões "Feita: …" e "Adiar: …" por linha, recarregando o detalhe; Bloqueadas sem botão; "Marco" textual quando `marco`; "projeto pausado" textual quando `pausada`.

- [ ] **Step 1: Testes que falham:** `Feita numa atividade do projeto chama POST /atividades/2/concluir e recarrega o detalhe`; `Adiar para amanhã chama PATCH /atividades/2 com vence_em de amanhã`; `bloqueada não tem botões e mostra "espera: …"`; `marco aparece como Marco`; `atividade de projeto pausado mostra "projeto pausado"`.
- [ ] **Step 2: Rodar e ver falhar:** `cd painel && npx vitest run tests/projetos.test.tsx`.
- [ ] **Step 3: Implementar**; se extrair o componente, manter os `aria-label` atuais de Atividades (`Feita: <texto>`, `Adiar: <texto>`) para o teste existente continuar passando.
- [ ] **Step 4: Rodar:** `cd painel && npx vitest run && npm run build`, depois `.venv/bin/pytest -q` (suíte inteira; ler o resumo "N passed").
- [ ] **Step 5: Commit** `feat(painel): concluir e adiar atividades dentro do projeto`.

### Task 7: ADR-035, BACKLOG e fechamento

**Files:**
- Create: `docs/adr/035-projetos-melhorias.md`
- Modify: `docs/BACKLOG.md` (item `PJ2`), `docs/STATUS.md` (uma linha), `docs/superpowers/specs/2026-10-27-projetos-melhorias-design.md` (Estado: implementado, aguarda ok)

- [ ] **Step 1:** Escrever a ADR-035 no formato da 034 (Contexto, Decisões, Como ficou, Consequências, Fora, Desfazer: `git revert` da branch; sem migração, nada a restaurar além do `config.yaml` e do SOUL do Hermes).
- [ ] **Step 2:** Item `PJ2` em "Aberto" do BACKLOG: dono R, 🔧, "implementado na branch `feat/projetos-melhorias`; só entra depois do `feat/projetos`; aguarda o ok para merge e instalação (73 ferramentas)"; pronto quando: "Hermes corrige um fato e apaga um gasto de teste depois do sim, e o projeto pausado deixa de avisar".
- [ ] **Step 3: Verificação final:** `.venv/bin/pytest -q` (ler o resumo) e `cd painel && npx vitest run && npm run build`; anotar as contagens no STATUS.
- [ ] **Step 4: Commit** `docs: ADR-035, BACKLOG PJ2 e STATUS`.
