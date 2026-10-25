# Hermes completo · Onda 1 (honestidade e família) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o Hermes grava pessoa, parentesco e pet ditados pelo Ricardo, nunca afirma gravação que não houve, e as respostas da família param de vir "desatualizadas".

**Architecture:** módulo novo `gabi/familia/pessoas.py` (criar/atualizar pessoa e pet, com histórico e desfazer em `pessoa_historico`), duas ferramentas MCP no escopo `familia`, frescor do envelope por ferramenta (`FONTES_DA_FERRAMENTA`), regra de honestidade no SOUL e um script de conferência (`tools/auditar_promessas.py`) que lê o `state.db` do Hermes.

**Tech Stack:** Python 3 (stdlib, sqlite3, FastAPI, MCP), pytest; painel React/TS (vitest).

**Spec:** `docs/superpowers/specs/2026-10-25-hermes-completo-design.md` (seção "Onda 1").

**Pré-requisito:** a branch sai da `main` **depois** do merge de `feat/documentos` (precisa de `CadastrosDocumentos.tsx`, das ferramentas `documentos_*` e da migração 0081). Branch `feat/hermes-onda1`, worktree `~/gabi-brain-hermes1`.

**Correção da spec (achado ao planejar):** o "Dados até 14/10" não vem de o Nibo contar no `dados_ate`. O Nibo está em `fontes.em_espera` e não conta. O Hermes leu a `ultima` do Nibo (14/10) na lista `fontes`. Além disso, `desatualizado` sai `True` por `bancos_antigos` (C6 Empresas). A solução da spec continua a mesma: uma ferramenta sem fonte declarada recebe envelope sem `fontes`, sem `bancos_antigos` e com `desatualizado=False`.

## Global Constraints
- Escopo MCP das ferramentas novas: `familia`. Quem grava: `QUEM = "hermes"`. `decisao.origem = 'familia'`.
- Gravação direta do que o Ricardo dita (R1 parcial, ADR-025/028), sempre com linha em `pessoa_historico` e Desfazer. Nada é gravado a partir de texto de terceiros.
- Privacidade é decisão do Ricardo: nada é mascarado por iniciativa do sistema.
- `decisao.o_que`, logs e `chamada_mcp` sem nome de terceiros, telefone ou número de documento; só pessoa_id, campo e ação (como `contato._auditar`).
- Erros com código fixo: `pessoa_ambigua`, `valor_invalido`, `campo_invalido`, `nao_encontrado`, `conflito`, `requisicao_invalida`.
- `parentesco`, `apelido` e `observacao`: texto até `contato.MAX_TEXTO`. `nascimento`: `YYYY-MM-DD`.
- Nenhuma migração nova. Usar `pessoa`, `pet` e `pessoa_historico`, que já existem.
- ADR **028**. Ler o resumo do pytest. Painel: `cd painel && npm test && npm run build`.

## Review Focus
1. Nome já cadastrado ditado de novo ("Carla Noce Della Torre é mãe da Gigi") → atualiza a Carla existente, não cria duplicata. Teste na Task 2.
2. Nome que casa com duas pessoas → `pessoa_ambigua` com candidatos e nada gravado. Teste na Task 2.
3. Desfazer a criação de uma pessoa que já recebeu outra mudança depois → `conflito`, nada some. Teste na Task 2.
4. Uma frase com "anotei" após uma ferramenta de escrita que devolveu `erro` conta como promessa sem gravação. Teste na Task 4.
5. A ferramenta de família responde sem `fontes`, sem `bancos_antigos` e com `desatualizado=False`, mesmo com banco parado. As de dinheiro continuam como hoje. Teste na Task 1.

---

### Task 1: Frescor do envelope por ferramenta

**Files:**
- Modify: `gabi/envelope.py` (`envelope`)
- Modify: `gabi/mcp/servidor.py` (`FONTES_DA_FERRAMENTA`, `executar`)
- Test: `tests/test_envelope.py`, `tests/mcp/test_servidor.py`

**Interfaces:**
- Produces: `envelope(con, dados, agora=None, fontes: tuple[str, ...] | None = None) -> dict`.
  - `None` = comportamento atual.
  - Uma tupla filtra as fontes da lista e o cálculo.
  - `()` devolve `{"dados_ate": None, "desatualizado": False, "proxima_rodada", "fontes": [], "dados"}`, sem `bancos_antigos`.
- Produces: `servidor.FONTES_DA_FERRAMENTA: dict[str, tuple | None]`, com toda ferramenta de `ESCOPOS_FERRAMENTAS`.
  - `None` (todas): ferramentas de dinheiro, `resumo_manha`, `fechamento_dia` e `agenda_financeira`.
  - `("agenda",)`: `agenda_listar` e `propor_evento`.
  - `("correio",)`: `email_listar`.
  - `()`: `familia_*`, `documentos_*`, `bens_listar`, `decisoes_abertas`, `decisao_responder`, `regras_sugerir`, `classificar_lancamento` e `propor_teams`.

- [ ] **Step 1: testes que falham.**
  - `test_envelope_fontes_vazias_nunca_desatualizado`: banco com `dinheiro.sync_banco` antigo e rodada de open-finance velha; `envelope(con, {}, agora, fontes=())` → `desatualizado is False`, `fontes == []`, `"bancos_antigos" not in`.
  - `test_envelope_fontes_filtradas`: `fontes=("agenda",)` → só `agenda` em `fontes`, e `dados_ate` é a última da agenda.
  - `test_envelope_padrao_inalterado`: sem `fontes`, a mesma saída de antes.
  - `test_toda_ferramenta_declara_fontes`: `set(FONTES_DA_FERRAMENTA) == set(ESCOPOS_FERRAMENTAS)`.
  - `test_familia_listar_sem_fontes`: chamar `familia_listar` pelo servidor de teste com banco desatualizado → `desatualizado is False`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_envelope.py tests/mcp/test_servidor.py -q` → FAIL.
- [ ] **Step 3:** implementar. Em `executar`, `envelope(con, dados, agora=agora_fn(), fontes=FONTES_DA_FERRAMENTA[ferramenta])`.
- [ ] **Step 4:** mesmos testes → PASS; a suíte inteira passa.
- [ ] **Step 5:** commit `feat(envelope): frescor por ferramenta; família sem fontes`.

### Task 2: Pessoa e pet com histórico e desfazer

**Files:**
- Create: `gabi/familia/pessoas.py`
- Modify: `gabi/familia/contato.py` (`TEXTOS` ganha `"observacao"`; booleano `falecido`; `desfazer` delega os campos especiais)
- Test: `tests/familia/test_pessoas.py`, `tests/familia/test_contato.py`

**Interfaces:**
- Consumes: `fichas.resolver_pessoa`, `fichas.ErroFamilia`, `contato.atualizar`, `contato._historico`, `contato._auditar`, `gabi.envios.propostas.normalizar_nome`, `gabi.db.transacao`.
- Produces:
  - `pessoas.registrar_pessoa(con, *, nome: str, parentesco: str, apelido: str = "", nascimento: str = "", falecido: bool = False, observacao: str = "", quem: str, agora) -> dict`, que devolve `{"pessoa_id", "criada": bool, "mudancas": [{"campo", "antes", "depois", "historico_id"}]}`.
  - `pessoas.registrar_pet(con, *, nome: str, especie: str, raca: str = "", nascimento: str = "", dono: str = "", quem: str, agora) -> dict`, que devolve `{"pet_id", "criado": bool, "historico_id"}`.
  - `pessoas.listar_pets(con) -> list[dict]`, com itens `{id, nome, especie, raca, nascimento, dono}`.
  - `pessoas.desfazer_especial(con, h, quem, agora) -> dict`, chamado por `contato.desfazer` quando `h["campo"] == "criada"` ou começa com `"pet:"`.
- Regras:
  - **Resolver:**
    - Tenta `resolver_pessoa(nome)`, depois `resolver_pessoa(apelido)` se houver apelido.
    - Exatamente 1 → atualiza.
    - `pessoa_ambigua` com candidatos não vazios → propaga o erro, sem gravar.
    - Candidatos vazios → cria.
  - **Criar:**
    - `id` = slug do primeiro nome: `normalizar_nome`, espaços viram `-`.
    - Se o id já existe: slug do nome completo; se esse também existe: sufixo `-2`, `-3`.
    - Insere em `pessoa` (`nome`=primeiro nome, `papel='familia'`, `dados={"nome_completo": nome}`, `origem='hermes'`).
    - Grava o histórico `campo='criada'`, `antes=None`, `depois={"nome": nome}`.
    - Depois aplica os campos com `contato.atualizar(..., acao="definir")`. Campo vazio não é aplicado. Valor igual ao atual não gera histórico.
  - **Booleano:** `falecido` só é gravado quando `True`, em `dados.falecido`.
  - **Pet:**
    - Linha em `pet` (`id` = slug do nome; `dados={raca, nascimento, dono}`, onde `dono` é o pessoa_id resolvido; dono ambíguo → `pessoa_ambigua`).
    - Nome existente → atualiza a mesma linha.
    - Histórico em `pessoa_historico` com `pessoa_id='pets'` (garantir a linha com `insert or ignore into pessoa(id, nome, papel, dados, origem) values ('pets','Pets','pets','{}','sistema')`), `campo=f"pet:{id}"`, e `antes`/`depois` com o dict do pet (`None` quando não existia).
  - **Desfazer especial:**
    - `criada`: se houver mudança não desfeita posterior para essa pessoa → `conflito`; senão `excluido_em=agora`.
    - `pet:`: se o pet atual difere do `depois` → `conflito`; senão restaura o `antes` (`None` → apaga a linha).

- [ ] **Step 1: testes que falham** (`tests/familia/test_pessoas.py`, usando `tests/familia/apoio.py`).
  - `test_cria_pessoa_nova_com_parentesco`: "Chafic Esper", "irmão" → `criada True`, `pessoa_id == "chafic"`, ficha com `parentesco == "irmão"` e `nome_completo == "Chafic Esper"`, e 2 linhas de histórico (`criada`, `parentesco`).
  - `test_atualiza_existente_sem_duplicar`: "Carla Noce Della Torre", "ex-esposa, mãe da Gigi", com a Carla na base → `criada False`, e `count(pessoa)` não muda.
  - `test_ambiguo_nao_grava`: duas pessoas que casam → `ErroFamilia("pessoa_ambigua")` com 2 candidatos, e `count(pessoa_historico)` igual.
  - `test_id_colide_usa_nome_completo`: já existe `sandra` → "Sandra Maria Esper" vira `sandra-maria-esper`.
  - `test_falecido_e_observacao`: "Salim Esper", "pai", `falecido=True` → `dados.falecido is True`.
  - `test_desfazer_criada_exclui` e `test_desfazer_criada_com_mudanca_posterior_conflito`.
  - `test_pet_cria_e_atualiza`: Cookie, "cachorro", raca "shih-tzu", nascimento "2017-07-19", dono "Ricardo" → `listar_pets` tem o Cookie com `dono == "ricardo"`; registrar de novo com outra raça atualiza, sem duplicar.
  - `test_desfazer_pet_novo_apaga`.
  - `test_nascimento_invalido` → `valor_invalido`, nada gravado.
  - `test_auditoria_sem_nome`: `decisao.o_que` não contém "Chafic".
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/familia -q` → FAIL.
- [ ] **Step 3:** implementar. Tudo de uma chamada fica numa transação só: `contato.atualizar` abre `transacao(imediata=True)`, então extraia o miolo para `contato._aplicar(con, ...)`, sem transação, e chame-o dentro da transação de `registrar_pessoa`.
- [ ] **Step 4:** `tests/familia` → PASS; a suíte inteira passa.
- [ ] **Step 5:** commit `feat(familia): registrar pessoa e pet com histórico e desfazer`.

### Task 3: Ferramentas MCP, SOUL e painel

**Files:**
- Modify: `gabi/mcp/ferramentas_familia.py` (2 ferramentas; `familia_listar` com `pets`; `ESCOPOS`)
- Modify: `gabi/mcp/servidor.py` (`FONTES_DA_FERRAMENTA` com as 2 novas = `()`)
- Modify: `deploy/hermes/SOUL.md`; `docs/fontes/hermes.md` (`python -m tools.gerar_hermes`)
- Modify: `painel/src/telas/CadastrosDocumentos.tsx` (rótulo do histórico)
- Test: `tests/mcp/test_familia.py`, `tests/mcp/test_servidor.py` (conjuntos e contagens), `tests/mcp/test_hermes.py`, `painel/tests/documentos.test.tsx`

**Interfaces:**
- Consumes: Task 2 (`registrar_pessoa`, `registrar_pet`, `listar_pets`), Task 1 (`FONTES_DA_FERRAMENTA`).
- Produces:
  - `familia_registrar_pessoa(nome: str, parentesco: str, apelido: str = "", nascimento: str = "", falecido: bool = False, observacao: str = "") -> dict`.
  - `familia_registrar_pet(nome: str, especie: str, raca: str = "", nascimento: str = "", dono: str = "") -> dict`.
  - As duas devolvem o resultado da Task 2 mais `link` (`_com_link(con, r, "#cadastros/documentos")`).
  - `familia_listar` → `{"itens": [...], "pets": [...]}`.
- Docstrings, que o Hermes lê:
  - "Grava direto o que o Ricardo ditou … Use na mesma resposta em que ele contar quem é a pessoa; só diga que anotou depois do ok desta ferramenta".
  - "Nome ambíguo volta com candidatos: pergunte qual".
  - A frase padrão de dado de terceiros, igual à das outras ferramentas.
- SOUL, parágrafo novo "Gravar de verdade":
  - "Nunca diga 'anotado', 'registrei', 'salvei', 'guardei' ou 'atualizei' sem ter chamado uma ferramenta de escrita do brain que devolveu ok nesta resposta; cite o que foi gravado."
  - "Se não houver ferramenta para gravar aquilo, diga: 'Não tenho como gravar isso no brain; fica só nesta conversa.'"
  - "Pessoa, parentesco, apelido, nascimento → familia_registrar_pessoa (ou familia_atualizar_contato para telefone, e-mail e endereço); pet → familia_registrar_pet."
- Painel: no bloco de histórico, `campo === "criada"` mostra "Pessoa criada: {depois.nome}"; `campo` começando com `"pet:"` mostra "Pet: {(depois ?? antes).nome}"; o Desfazer não muda.

- [ ] **Step 1: testes que falham.**
  - MCP: registrar pessoa nova e existente; ambíguo volta `erro: pessoa_ambigua` com os candidatos na mensagem; pet; `familia_listar` tem `pets`; sem escopo `familia` → `sem_escopo`; `chamada_mcp` com status `ok`; o envelope das 2 ferramentas tem `desatualizado False`.
  - `test_servidor`: as contagens do escopo `familia` e do total sobem em 2.
  - `test_hermes`: o SOUL contém "Gravar de verdade" e as duas ferramentas novas.
  - vitest: o histórico com `campo: "criada"` mostra "Pessoa criada: Chafic Esper"; com `campo: "pet:cookie"` mostra "Pet: Cookie"; o clique em Desfazer faz POST em `/api/v1/familia/historico/{id}/desfazer`; zero `console.error`.
- [ ] **Step 2:** FAIL (pytest focado e `npx vitest run tests/documentos.test.tsx`).
- [ ] **Step 3:** implementar e regerar `docs/fontes/hermes.md`.
- [ ] **Step 4:** a suíte pytest inteira, `npm test` e `npm run build` → PASS.
- [ ] **Step 5:** commit `feat(hermes): registrar pessoa e pet pelo chat; regra de gravar de verdade`.

### Task 4: Conferência de promessas, ADR e fechamento

**Files:**
- Create: `tools/auditar_promessas.py`, `tests/tools/test_auditar_promessas.py`, `docs/adr/028-hermes-completo.md`
- Modify: `docs/runbook.md` (seção `#hermes-onda1`), `docs/STATUS.md`, `docs/BACKLOG.md`, `docs/ARQUITETURA.md` (uma linha)

**Interfaces:**
- Produces: `auditar_promessas.promessas_sem_escrita(state_db: Path, desde: dt.datetime) -> list[dict]`, com itens `{quando, sessao, trecho}`. `main(argv)` imprime uma linha por caso e sai 0. `--desde YYYY-MM-DD` tem como padrão 7 dias atrás. O banco é aberto com `?mode=ro`.
- Algoritmo:
  - Sessões com `source in ('telegram','whatsapp')`.
  - Para cada mensagem `role='assistant'` com `content` que casa `r"\b(anotad|anotei|registr|salv|guard|atualiz)\w*"` (sem caixa), olhe as mensagens `role='tool'` da mesma sessão entre a última mensagem `role='user'` anterior e ela.
  - É escrita a mensagem com `tool_name` em `{"mcp__gabi_brain__" + n for n in ESCRITAS}` cujo `content` não contém `'"erro"'`.
  - `ESCRITAS`: `familia_atualizar_contato`, `familia_registrar_pessoa`, `familia_registrar_pet`, `familia_propor_documento`, `decisao_responder`, `classificar_lancamento`, `regras_sugerir`, `propor_evento`, `propor_teams`.
  - Sem nenhuma escrita → é caso.
  - `trecho` = os primeiros 80 caracteres, sem quebras de linha.
  - `timestamp` é epoch em segundos (float).
- ADR-028:
  - decisões e exceções da spec (Onda 1 detalhada; Ondas 2 e 3 por referência);
  - o "Correção da spec" acima;
  - a decisão de privacidade do Ricardo (25/10).
- Runbook, passos de instalação:
  - `sudo ~/instalar-brain.sh`;
  - acrescentar `familia_registrar_pessoa` e `familia_registrar_pet` em `tools.include` de `~/.hermes/config.yaml`, com backup antes (`config.yaml.bak-antes-onda1`);
  - instalar o SOUL (`deploy/hermes/SOUL.md` → `~/.hermes/SOUL.md`, com backup);
  - reiniciar o gateway do Hermes;
  - `/new` no Telegram e no WhatsApp;
  - rodar `python -m tools.auditar_promessas` e conferir.

- [ ] **Step 1: testes que falham** (state.db sintético criado no teste com as colunas `sessions(id, source)` e `messages(id, session_id, role, content, tool_name, timestamp)`).
  - `test_promessa_sem_ferramenta_e_caso`: user "chafic é meu irmão" → assistant "Anotado! Chafic…" sem tool → 1 caso.
  - `test_promessa_com_escrita_ok_nao_e_caso`: tool `mcp__gabi_brain__familia_registrar_pessoa` com conteúdo ok entre as duas → 0.
  - `test_escrita_com_erro_e_caso` (Review Focus 4).
  - `test_leitura_nao_conta`: só `familia_consultar` → 1 caso.
  - `test_cli_ignora_antes_de_desde`.
  - `test_somente_leitura`: o arquivo continua com o mesmo `mtime`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar e escrever a ADR e as docs. **Step 4:** a suíte inteira → PASS.
- [ ] **Step 5:** commit `feat(tools): conferência de promessas do Hermes; ADR-028`.
- [ ] **Step 6 (depois do merge, com autorização do Ricardo):** instalar pelo runbook. O assistente aplica o que o Ricardo já ditou ao Hermes em 24/10 (lido do `state.db`: irmãos, mãe, pai falecido, sobrinhos, ex-esposas, companheira, filhas, a dona do apto da Gigi e o Cookie) com `registrar_pessoa`/`registrar_pet`, `quem='ricardo (ditado ao Hermes em 24/10, via Claude)'`. Depois mostra a lista ao Ricardo para ele conferir. Confere também com `familia_listar` e `auditar_promessas` (0 casos novos).
