# gabi-finance — Corte do gabi-brain · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar esta cópia do `gabi-brain` num serviço só financeiro (`gabi-finance`), com a suíte verde a cada passo e pronto para a virada na VPS.

**Architecture:** Corte por remoção guiada pelo grafo de imports: o núcleo (`gabi/dinheiro`, `gabi/cobrar`, `gabi/decisoes.py`) e a base ficam; tudo o que só serve a agenda, e-mail, Teams, contatos, envios, família, documentos, projetos e atividades sai, com os seus testes. Os pontos de costura (API, MCP, avisos, Telegram, resumo da manhã, fontes/ponte, painel, deploy) são reduzidos ao financeiro. Uma migração apaga as tabelas que sobram sem uso.

**Tech Stack:** Python 3.13, FastAPI, SQLite (WAL), servidor MCP (`mcp`), pytest + ruff; painel React/TS (vitest, build); systemd; Tailscale serve.

**Spec:** `docs/superpowers/specs/2026-11-17-gabi-finance-design.md`

## Global Constraints

- Base: `main` deste repositório = `backup-vps-2026-11-17` (`0422aad`) do `gabi-brain` + o spec. Trabalho na branch `corte`; nada vai para a `main` sem o fim da revisão.
- **Comportamento financeiro não muda.** Nenhum teste de `tests/dinheiro`, `tests/cobrar` ou de rotas/MCP financeiros pode ser apagado ou enfraquecido; só se apagam testes de módulos que saem. Se um teste financeiro quebrar, o corte está errado.
- Fica (spec, "O que fica"): `gabi/dinheiro`, `gabi/cobrar`, `gabi/decisoes.py`, `db`, `rodada`, `bruto`, `envelope`, `identidade`, `acesso`, `agentes`, `backup`, `exportacao`, `mascara`, `hoje`, `api`, `avisos` (financeiro), `telegram` (financeiro), `dia` (bloco dinheiro), fontes `mcpai`, `nibo`, `nibo_escrita`, `ponte`, `servico`, `roteador`, `ambiente`, `_http`, `tokens`, MCP financeiro.
- Tabela `pessoa` (id, nome, papel), `conta.usuarios`, `gastador_regra` e "para quem" ficam (F6).
- Ponte só com `mcpai` e `nibo` (F5). Regra R5 mantida: só o serviço de fontes tem rede e token.
- MCP: nome do servidor `gabi_finance`; nomes das ferramentas financeiras **iguais** aos de hoje (F8).
- Avisos no Telegram só financeiros; resumo da manhã só com o bloco dinheiro (F7).
- Nomes na VPS (F9): usuário `gabifinance`; `/opt/gabi-finance`, `/var/lib/gabi-finance`, `/var/backups/gabi-finance`, `/etc/gabi-finance/`, `/run/gabi-finance/`; units `gabi-finance-*`; host `gabi-finance.tail985643.ts.net`.
- Testes: `/tmp/gabi-venv/bin/python -m pytest -q` (venv com `requirements.lock` + pytest + ruff; criar com `python3 -m venv /tmp/gabi-venv && /tmp/gabi-venv/bin/pip install -q -r requirements.lock pytest ruff` se faltar). Lint: `/tmp/gabi-venv/bin/ruff check gabi tools tests`. Painel: `cd painel && npm ci && npx vitest run && npm run build`.
- Falha pré-existente conhecida: `tests/test_obter_token_teams.py::test_main_gravar_falhando_nao_mostra_o_token` (roda como root). Sai junto com o módulo Teams na Task 5.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ao fim de cada task: suíte inteira verde (exceto a falha conhecida até a Task 5) e ruff limpo.

## Pré-flight (antes da Task 1)

- [ ] `git checkout -b corte`
- [ ] Rodar a suíte e anotar a contagem de base (esperado ~3.234 passed, 3 skipped, 1 failed conhecido).
- [ ] Gerar o grafo de imports (script em `tools/grafo_imports.py`, Task 1) e salvar a lista de módulos que **saem** em `docs/corte/saem.txt`.

---

### Task 1: Grafo de imports e lista do corte

**Files:**
- Create: `tools/grafo_imports.py`
- Create: `docs/corte/saem.txt`, `docs/corte/costuras.md`
- Test: `tests/test_grafo_imports.py`

**Interfaces:**
- Produces: `python -m tools.grafo_imports --fica <prefixos...>` imprime (a) o fecho de imports do que fica, (b) os módulos de `gabi/` fora do fecho, (c) as "costuras": módulos que ficam e importam algo que sai, com arquivo:linha.

- [ ] **Step 1:** Teste com um pacote falso em `tmp_path` (a importa b; c importa a e d; fica=[a]) → fecho {a,b}, saem {c,d}, nenhuma costura; e outro caso em que um módulo que fica importa um que sai → costura listada com arquivo:linha.
- [ ] **Step 2:** Implementar com `ast` (ImportFrom com `module` começando por `gabi` e também `from gabi.x import y` onde `y` é submódulo), sem importar nada.
- [ ] **Step 3:** Rodar com `--fica gabi.dinheiro gabi.cobrar gabi.decisoes gabi.db gabi.rodada gabi.bruto gabi.envelope gabi.identidade gabi.acesso gabi.agentes gabi.backup gabi.exportacao gabi.mascara gabi.hoje gabi.api gabi.avisos gabi.telegram gabi.dia gabi.fontes.mcpai gabi.fontes.nibo gabi.fontes.nibo_escrita gabi.fontes.ponte gabi.fontes.servico gabi.fontes.roteador gabi.fontes.ambiente gabi.fontes._http gabi.fontes.tokens gabi.mcp.servidor gabi.mcp.tokens gabi.rotas.dinheiro gabi.rotas.gastos gabi.rotas.cadastros gabi.rotas.despesas gabi.rotas.cobrar gabi.rotas.decisoes gabi.rotas.avisos gabi.rotas.agentes gabi.rotas.contagens`. Gravar `saem.txt` (um módulo por linha) e `costuras.md` (tabela: módulo que fica · importa · arquivo:linha · o que fazer). Em `costuras.md`, para cada costura, escrever a ação: "remover o uso", "trazer a função para o módulo que fica" ou "o módulo que fica sai também" — com uma linha de motivo.
- [ ] **Step 4:** Testes + ruff; commit `feat(corte): grafo de imports e lista do corte`.

> As Tasks 2–5 executam `costuras.md`. Toda decisão "fica/sai" que não estiver no spec é registrada lá com motivo.

### Task 2: Fontes e ponte só financeiras

**Files:** `gabi/fontes/ambiente.py`, `gabi/fontes/ponte.py`, `gabi/fontes/servico.py`, `gabi/fontes/roteador.py`, `gabi/decisoes.py` (linhas 74–75: `endereco` de `correio.regras` e `normalizar_telefone` de `contatos.telefone`), testes de `tests/fontes`.

- [ ] **Step 1:** Ajustar os testes de fontes que ficam para esperar só `nibo` e `mcpai` (ex.: `fontes_do_ambiente()` devolve só as chaves financeiras; o roteador recusa `google_email`, `graph_ness`, `openrouter`, `paperless` com o mesmo erro de fonte desconhecida que já usa). Rodar: falham.
- [ ] **Step 2:** Reduzir `ambiente`, `ponte` (remover `PonteAgenda`, `PonteEmail`, `PonteGraph`, `PonteModelo`), `servico`, `roteador` ao par `mcpai`/`nibo`. Em `decisoes.py`, trazer `endereco` e `normalizar_telefone` como funções privadas do próprio módulo (copiar o corpo com o teste que já os cobre), para `decisoes` não depender de `correio`/`contatos`.
- [ ] **Step 3:** Suíte inteira; os testes que quebram só por importar fontes removidas pertencem a módulos que saem — marcar em `costuras.md` e deixar para a Task 5 (não apagar aqui). Ruff.
- [ ] **Step 4:** Commit `refactor(fontes): ponte só com mcp.ai e Nibo`.

### Task 3: API, rotas e MCP financeiros

**Files:** `gabi/api.py` (linhas 159–199: `include_router`), `gabi/rotas/cadastros.py` (só a parte financeira: despesas, cobrança, equivalências, regras — o resto sai), `gabi/mcp/servidor.py`, `gabi/mcp/ferramentas_*.py`, `gabi/mcp/tokens.py`, testes de `tests/rotas`, `tests/mcp`, `tests/test_api.py`.

- [ ] **Step 1:** Teste novo `tests/test_corte_superficie.py`: (a) as rotas registradas no app são exatamente as de `dinheiro`, `gastos`, `cadastros` (financeiro), `despesas`, `cobrar`, `decisoes`, `avisos`, `agentes`, `contagens` + as rotas base de hoje (saúde, identidade, estáticos); (b) `ferramentas_do_hermes()` contém só ferramentas financeiras — lista exata gerada a partir das ferramentas de hoje cujo módulo fica, gravada no teste; (c) o servidor MCP se anuncia como `gabi_finance`. Rodar: falha.
- [ ] **Step 2:** Tirar os `include_router` que saem; reduzir `rotas/cadastros.py`; no MCP, remover os módulos `ferramentas_*` não financeiros e, nos mistos (`ver`, `agir`, `dec`, `prop`, `assistente`), remover só as ferramentas não financeiras — as financeiras ficam com nome, assinatura e resposta idênticos. Escopos de token que só serviam a ferramentas removidas saem de `tokens.py`; tokens existentes com esses escopos continuam válidos (o escopo some, o token não).
- [ ] **Step 3:** Suíte + ruff. Commit `refactor(api,mcp): superfície só financeira; servidor gabi_finance`.

### Task 4: Avisos, Telegram e resumo da manhã financeiros

**Files:** `gabi/avisos.py`, `gabi/telegram.py`, `gabi/dia.py`, `gabi/rotas/dia.py` (sai se só servia à tela Hoje), testes correspondentes.

- [ ] **Step 1:** Testes: `gerar_avisos` não chama mais `_hermes_parado`, `_google_parado`, `_teams_sem_resposta`, `_documento_vence`, atividades, projetos nem convites; continuam `rodada_parada`, `saldo_divergente`, `exportacao_parada`, `bancos_desatualizados`, `conta_atrasada`, `cobrada_apos_cancelar`, `vence_hoje`, `vence_em_breve`, `valor_diferente`, `lancamento_sem_conversao`, `servico_falhou` (units `gabi-finance-*`). Resumo da manhã: só o bloco dinheiro (saldo, atrasadas, vence hoje/semana), sem agenda nem e-mail. Rodar: falham.
- [ ] **Step 2:** Reduzir os três módulos. `telegram.py` mantém o envio e o formato de hoje para os tipos que ficam.
- [ ] **Step 3:** Suíte + ruff. Commit `refactor(avisos): avisos e resumo só financeiros`.

### Task 5: Remover módulos, testes e fontes que saem

**Files:** tudo em `docs/corte/saem.txt` e os testes desses módulos (inclui `tests/test_obter_token_teams.py`), `tools/` que só servem a eles (`obter_token_google.py`, `obter_token_teams.py`, `sonda_teams_ness.py`, `comparar_agenda.py`, `carga_familia.py`, `capturas.py` se não for financeiro — decidir pelo grafo), `gabi/static` se só servir telas que saem.

- [ ] **Step 1:** `git rm` em lote. Rodar o grafo de novo: nenhum módulo que fica importa algo inexistente; `grep -rn "gabi\.\(agenda\|correio\|teams\|contatos\|envios\|familia\|documentos\|projetos\|atividades\|anexos\|antecipar\|reuniao\|revisao\|transcricao\|visao_pdf\)" gabi tools tests` vazio.
- [ ] **Step 2:** Suíte inteira **sem falhas** (a falha conhecida saiu com o Teams) + ruff. Anotar a contagem nova e quantos testes saíram, por pasta, no corpo do commit.
- [ ] **Step 3:** Commit `refactor(corte): remove módulos não financeiros e seus testes`.

### Task 6: Migração do corte de tabelas

**Files:** Create `migrations/0090_corte_financeiro.sql`; Test `tests/test_migracao_corte.py`.

- [ ] **Step 1:** Teste: num banco migrado até 0090, (a) toda tabela que algum módulo que fica referencia (lista gerada por `grep` de nomes de tabela em `gabi/` + `migrations/0090` anterior — gravar a lista no teste) existe; (b) nenhuma das tabelas não financeiras existe (lista explícita: agenda, e-mail, Teams, contatos, envios, família/documentos/bens/pets, projetos, atividades, anexos, escuta, memória e as `*_legado`); (c) `pessoa`, `conta`, `gastador_regra`, `decisao`, `acesso`, `matriz_acesso`, `token_agente`, `chamada_mcp`, `aviso`, `rodada` existem. Rodar: falha.
- [ ] **Step 2:** Escrever a migração com `drop table if exists` na ordem que respeita chaves estrangeiras (filhas antes); `pragma foreign_keys` como o `migrar` já trata. Sem mexer em linhas de `pessoa`.
- [ ] **Step 3:** Suíte inteira (o banco-modelo do `conftest` passa a incluir 0090) + ruff. Commit `feat(db): migração 0090 remove tabelas não financeiras`.

### Task 7: Painel só financeiro

**Files:** `painel/src/navegacao.ts`, `painel/src/App.tsx`, `painel/src/telas/*` (saem: `Trabalho/`, `Projetos.tsx`, `Atividades.tsx`, `Envios.tsx`, `ContatosPropostas.tsx`, `CadastrosAgenda.tsx`, `CadastrosContatos.tsx`, `CadastrosCorreio.tsx`, `CadastrosDocumentos.tsx`, `CadastrosTeams.tsx`, `Gabi/Qualidade.tsx` se a rota de qualidade saiu), testes vitest correspondentes, `tests/test_amostras_painel.py`.

- [ ] **Step 1:** Ajustar o teste de navegação para a lista final de áreas/abas (Caixa, Cobrar, Gastos, Cadastros financeiros, Regras, Gabi › Agentes). Rodar: falha.
- [ ] **Step 2:** Remover telas e entradas de navegação; tela inicial passa a ser Caixa › A pagar.
- [ ] **Step 3:** `npx vitest run && npm run build` verdes; suíte Python verde. Commit `refactor(painel): só telas financeiras`.

### Task 8: Deploy e nomes da VPS

**Files:** `deploy/*` (renomear `gabi-brain-*` → `gabi-finance-*`; remover units de agenda, anexos, contatos, correio, documentos, teams), `deploy/instalar.sh`, `deploy/hermes/SOUL.md` (só a parte financeira, com prefixo `mcp__gabi_finance__`), `gabi/api.py` e demais defaults de caminho (`GABI_BANCO` → `/var/lib/gabi-finance/gabi.db` etc.), `tools/auditar_promessas.py` (prefixo e lista `ESCRITAS` só financeira), `tools/gerar_hermes.py`, `tests/test_deploy.py`.

- [ ] **Step 1:** `tests/test_deploy.py` passa a exigir: só units `gabi-finance-*`; `User=gabifinance`; caminhos `/opt/gabi-finance`, `/var/lib/gabi-finance`, `/run/gabi-finance`, `/etc/gabi-finance/`; nenhuma ocorrência de `gabi-brain` em `deploy/` nem em defaults de `gabi/`. Rodar: falha.
- [ ] **Step 2:** Renomear e ajustar. `instalar.sh` cria o usuário `gabifinance`, pastas e venv, instala as units **desligadas** (a virada liga).
- [ ] **Step 3:** Suíte + ruff. Commit `chore(deploy): nomes e caminhos do gabi-finance`.

### Task 9: Documentação farta e roteiro da virada

> Pedido do Ricardo (17/11): **documentar fartamente o repositório do gabi-finance no GitHub.** Quem abrir o repositório sem contexto precisa entender o que é, como funciona, como instalar, operar, recuperar e evoluir.

**Files:** `README.md` (novo, completo), `docs/ARQUITETURA.md` (reescrito para o gabi-finance, com diagrama), `docs/STATUS.md` (zerado), `docs/runbook.md` (só seções financeiras, revisadas), Create `docs/virada.md`, Create `docs/modulos.md` (um verbete por módulo de `gabi/`: o que faz, tabelas que lê/escreve, quem chama, testes), Create `docs/dados.md` (cada tabela que fica: colunas, significado, quem escreve), Create `docs/mcp.md` (cada ferramenta: escopo, parâmetros, resposta, exemplo), Create `docs/painel.md` (cada tela: o que mostra, ações, rota da API), Create `docs/operacao.md` (timers e horários, logs, backup e restauração, rotação de tokens mcp.ai/Nibo, falhas comuns e como resolver), Create `docs/adr/039-corte-gabi-finance.md` (por que nasceu, o que saiu, decisões F1–F9), `docs/corte/` mantido como registro.

- [ ] **Step 0:** Escrever os documentos acima a partir do código final (não do plano). `README.md` abre com: o que é, de onde veio (gabi-brain → etapa 2 do esper-brain), arquitetura em 1 parágrafo + diagrama, instalação, operação, links para cada doc. Teste `tests/test_docs.py`: todo módulo de `gabi/`, toda ferramenta MCP e toda tabela do banco migrado aparece em `docs/modulos.md`, `docs/mcp.md` e `docs/dados.md` respectivamente (falha se faltar).

- [ ] **Step 1:** `docs/virada.md` com os comandos exatos dos 7 passos do spec e da volta, para o Ricardo rodar como root, incluindo: `sqlite3 .backup` (ou `python3 -c` com a API de backup) do banco do `gabi-brain` com os timers parados; aplicar migrações com o `migrar` do `gabi-finance`; mover tokens para `/etc/gabi-finance/` com permissão 600; `tailscale serve` do novo host; a conferência (script `tools/conferir_virada.py` que imprime saldos por conta, total A pagar do mês e projeção 30 dias de **um** banco — rodar contra os dois e comparar com `diff`); `config.yaml` do Hermes com backup e troca do servidor MCP; `/new`.
- [ ] **Step 2:** `tools/conferir_virada.py` + teste (banco de teste → saída determinística). Suíte + ruff.
- [ ] **Step 3:** Commit `docs: arquitetura, runbook e roteiro da virada do gabi-finance`.

---

## Self-review

- Spec F1–F9 cobertos: F1 pré-flight; F2 Task 7; F3 Task 6 + virada; F4 Task 9; F5 Task 2; F6 constraints + Task 6(c); F7 Task 4; F8 Task 3 + Task 8; F9 Task 8.
- Tasks 1–5 dependem da lista do grafo; decisões fora do spec ficam em `docs/corte/costuras.md` com motivo.
