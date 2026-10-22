# Teams da ness (aviso de mensagem sem atenção) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Avisar no Telegram quando há mensagem para o Ricardo no Teams da `resper@ness.com.br` (chat 1:1 ou menção em grupo) sem resposta há 2 horas úteis, sem guardar texto.

**Architecture:** O serviço de fontes (único com rede e segredos) ganha dois métodos de leitura do Graph (`teams_chats`, `teams_mensagens`) que já devolvem só metadado. Um coletor (`gabi/teams`, timer desligado) atualiza a tabela `teams_conversa`; `gabi/avisos.py` gera o aviso `teams_sem_resposta` e o revalida na entrega. Só a ness; ionic, canais e modelo ficam fora deste plano.

**Tech Stack:** Python 3, SQLite, FastAPI, pytest, systemd. Padrões a copiar: `gabi/fontes/graph_ness.py` (+ `tests/fontes/test_graph_ness_email.py`), `gabi/fontes/ponte.py`, `gabi/agenda/__main__.py`, `gabi/avisos.py`, `deploy/gabi-brain-correio.*`.

**Spec:** `docs/superpowers/specs/2026-10-20-teams-design.md` (e `2026-10-19-graph-ness-design.md`, parte 4).

## Global Constraints

- Só leitura (R2): nenhum método que envie, escreva, reaja ou apague; só `GET` ao Graph.
- Corpo, assunto e anexos nunca persistem nem aparecem em log, exceção, aviso ou resposta da ponte: o `$select` das mensagens não inclui `body` e a fonte devolve só `{id, quando, de_nome, de_eu, mencoes_eu}`.
- Conta vem do cadastro (`GraphNess._conta` rejeita as não cadastradas); só chats em que a conta é membro.
- Regra: chat 1:1 ou menção ao Ricardo em grupo; **2 horas úteis** sem resposta dele; um aviso por conversa; `teams.horas_uteis` = 2 e expediente `teams.expediente` = seg–sex 08:00–19:00 America/Sao_Paulo (`parametro`, lido como `avisos._parametro`).
- Segredos só em `/etc/gabi/graph-ness.env`. Timer instalado e **desligado**; nada ligado.
- Erro do Graph vira `ErroGraphNess` sem corpo de resposta; 429 encerra a conta na rodada (sem laço de retentativa); falha de um chat ou conta não derruba os outros.
- Mensagens em pt-BR; commits terminam com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

- Mensagem em grupo **sem** menção a ele não gera aviso (Task 5, Task 6).
- Ele respondeu pelo celular entre a coleta e o envio: o aviso fecha como resolvido, não é enviado (Task 6).
- Primeira coleta de uma conta não inunda com histórico: só a janela inicial de 24 h conta (Task 5).
- Mensagem de bot/aplicação, de sistema (entrou/saiu) ou apagada não conta (Task 2).
- Chat que devolve 403/404 (saiu do chat) é pulado; a conta segue (Task 5).
- Texto de mensagem nunca vaza em log, exceção, banco, aviso nem ponte (Tasks 2, 5, 6).
- Mensagem chegando às 23h ou no sábado: o relógio de 2 h úteis só corre no expediente (Task 4).

---

### Task 1: Sonda real do Graph (porta de verificação)

**Files:**
- Create: `tools/sonda_teams_ness.py`
- Modify: `docs/superpowers/specs/2026-10-20-teams-design.md` (§6, registrar o achado)

**Interfaces:**
- Consumes: `gabi.fontes.graph_ness.graph_ness_do_ambiente(env)`, `GraphNess._get(url, extra)` (privado: a sonda é ferramenta do dono, roda com o env do serviço de fontes).
- Produces: um achado escrito sobre (a) `GET /users/{conta}/chats?$expand=lastMessagePreview` responde 200, (b) `GET /chats/{id}/messages?$top=5&$select=id,createdDateTime,from,messageType,mentions,deletedDateTime` responde 200 por aplicativo, (c) se algum endpoint exige licença/medição (402/403), (d) forma de `from.user.id`, `mentions[].mentioned.user.id`, `chatType`.

- [ ] **Step 1: Escrever `tools/sonda_teams_ness.py`**: lê o env já carregado, faz as 3 chamadas acima na conta da ness e imprime **somente** status, `chatType`, contagens e nomes de campo (nunca `body`, `displayName` nem ids de mensagem). Pegar o caminho do runbook `#graph-ness` para executar com o ambiente do serviço (sem abrir o arquivo de segredo).
- [ ] **Step 2: Executar** como no teste real de 19/10 (runbook `#graph-ness`). Esperado: 200 nas 3 chamadas.
- [ ] **Step 3: Registrar o achado** na spec §6 (3-5 linhas) e, se (b) ou (c) falhar, **parar e avisar o Ricardo** antes das tasks seguintes (o desenho muda).
- [ ] **Step 4: Commit** `docs: achado da sonda do Teams da ness`.

---

### Task 2: Leitura de Teams em `GraphNess`

**Files:**
- Modify: `gabi/fontes/graph_ness.py` (métodos em `GraphNess`, helpers de módulo `_chat`, `_mensagem_teams`)
- Test: `tests/fontes/test_graph_ness_teams.py` (copiar `Token`, `Falso`, `graph()` de `test_graph_ness_email.py`)

**Interfaces:**
- Produces:
  - `GraphNess.teams_chats(conta: str) -> list[dict]` → `[{"chat_id": str, "tipo": "um_a_um"|"grupo", "ultima_em": str|None}]` (`oneOnOne`→`um_a_um`; `group` e `meeting`→`grupo`; `ultima_em` = ISO UTC de `lastMessagePreview.createdDateTime`; paginado por `_paginas`).
  - `GraphNess.teams_mensagens(conta: str, chat_id: str, desde: str | None) -> list[dict]` → `[{"id": str, "quando": str(ISO UTC), "de_nome": str, "de_eu": bool, "mencoes_eu": bool}]`, crescente por `quando`, só `quando > desde`.
  - Descarta: `messageType != "message"`, `deletedDateTime` preenchido, `from.application` (bot) ou sem `from.user`.
  - `de_eu`/`mencoes_eu` comparam com o id AAD da conta (`GET /users/{conta}?$select=id`, cacheado em `self._meu_ids`).
  - `chat_id` validado por regex (`^[0-9A-Za-z:@._-]{1,200}$`), senão `ErroGraphNess("chat inválido")`.

- [ ] **Step 1: Testes que falham** em `test_graph_ness_teams.py`: `test_chats_mapeia_tipos_e_ultima`, `test_mensagens_so_depois_de_desde_e_em_ordem`, `test_ignora_sistema_apagada_e_bot`, `test_de_eu_e_mencoes_eu_pelo_id_da_conta`, `test_conta_nao_cadastrada_levanta`, `test_chat_id_invalido_levanta`, `test_select_nao_pede_body` (assert que `"body" not in` o `$select` capturado em `http.chamadas`), `test_resposta_nao_traz_texto` (mensagem de fixture com `body.content="SEGREDO"`: `"SEGREDO" not in json.dumps(resultado)`), `test_erro_nao_vaza_corpo` (403 vira `ErroGraphNess` sem o corpo).
- [ ] **Step 2: Rodar** `pytest tests/fontes/test_graph_ness_teams.py -q` → falha (métodos inexistentes).
- [ ] **Step 3: Implementar** os dois métodos usando `_get`/`_paginas` e `$select=id,createdDateTime,from,messageType,mentions,deletedDateTime` mais `$orderby=createdDateTime desc` e `$top=50` nas mensagens; aplicar o ajuste do achado da Task 1 se os endpoints diferirem.
- [ ] **Step 4: Rodar** o arquivo de teste e `pytest tests/fontes -q` → verde.
- [ ] **Step 5: Commit** `feat(graph-ness): leitura de chats e mensagens do Teams (só metadado)`.

---

### Task 3: Ponte para o serviço de fontes

**Files:**
- Modify: `gabi/fontes/ponte.py` (`PERMITIDOS["graph_ness"]`, `PonteGraph`)
- Test: `tests/fontes/test_ponte.py`

**Interfaces:**
- Consumes: `GraphNess.teams_chats`, `GraphNess.teams_mensagens` (Task 2).
- Produces: `PonteGraph.teams_chats(conta) -> list[dict]` e `PonteGraph.teams_mensagens(conta, chat_id, desde) -> list[dict]`; resposta fora da forma (não lista, itens sem as chaves/tipos acima) levanta `ErroGraphNess("resposta inválida do serviço de fontes")`.

- [ ] **Step 1: Testes que falham**: `test_ponte_graph_teams_chats_valida_forma`, `test_ponte_graph_teams_mensagens_valida_forma`, `test_teams_metodos_estao_permitidos`, `test_metodo_de_escrita_do_teams_nao_existe` (nenhum nome em `PERMITIDOS["graph_ness"]` com `enviar|responder|apagar|reagir`).
- [ ] **Step 2: Rodar** → falha.
- [ ] **Step 3: Implementar** os dois wrappers (mesmo molde de `listar_calendarios`, validando `isinstance` e as chaves) e acrescentar `"teams_chats", "teams_mensagens"` ao `frozenset`.
- [ ] **Step 4: Rodar** `pytest tests/fontes -q` → verde.
- [ ] **Step 5: Commit** `feat(ponte): Teams da ness (leitura)`.

---

### Task 4: Migração e regra das 2 horas úteis

**Files:**
- Create: `migrations/0071_teams.sql`, `gabi/teams/__init__.py`, `gabi/teams/regra.py`
- Test: `tests/teams/__init__.py`, `tests/teams/test_regra.py`, `tests/test_esquema.py` (conferir se há lista de tabelas)

**Interfaces:**
- Produces (migração):
  - `teams_fonte(id integer primary key, conta text not null unique, estado text not null default 'a_decidir' check (estado in ('sim','nao','a_decidir')), coletada_em text, ultimo_erro text)`
  - `teams_conversa(conta text not null, chat_id text not null, tipo text not null check (tipo in ('um_a_um','grupo')), de_nome text, ultima_para_mim_em text, minha_ultima_resposta_em text, ultimo_aviso_em text, cursor text, primary key (conta, chat_id))`. Nenhuma coluna de texto de mensagem.
- Produces (regra):
  - `horas_uteis_entre(inicio: dt.datetime, fim: dt.datetime, expediente: tuple[dt.time, dt.time]) -> float` (só seg–sex dentro do expediente, em `America/Sao_Paulo`, datas com tz).
  - `pendente(conv: sqlite3.Row | dict, agora: dt.datetime, horas: float, expediente) -> bool`: verdadeiro se `ultima_para_mim_em` existe, `minha_ultima_resposta_em` é nula ou anterior a ela, `ultimo_aviso_em` é nulo ou anterior a ela, e `horas_uteis_entre(ultima_para_mim_em, agora) >= horas`.
  - `ler_config(con) -> tuple[float, tuple[dt.time, dt.time]]` com os padrões 2 e 08:00–19:00 (parâmetros `teams.horas_uteis`, `teams.expediente` como `"08:00-19:00"`).

- [ ] **Step 1: Testes que falham** em `test_regra.py`: `test_dentro_do_expediente_conta_o_tempo_corrido` (09:00→11:00 = 2,0), `test_noite_nao_conta` (18:00→09:00 do dia seguinte = 1,0 + 1,0 = 2,0 até 10:00), `test_fim_de_semana_nao_conta` (sex 18:00 → seg 09:00 = 2,0), `test_pendente_depois_de_duas_horas_uteis`, `test_resposta_posterior_nao_e_pendente`, `test_aviso_ja_enviado_para_a_mesma_mensagem_nao_repete`, `test_nova_mensagem_depois_do_aviso_volta_a_ser_pendente`, `test_config_padrao_e_parametros`, e em `tests/teams/test_migracao.py` `test_tabelas_sem_coluna_de_texto` (colunas das duas tabelas ⊂ lista fixa).
- [ ] **Step 2: Rodar** `pytest tests/teams -q` → falha.
- [ ] **Step 3: Escrever a migração** (comentário de cabeçalho como `0051`: "sem texto de mensagem") e implementar `regra.py` (soma por janelas diárias, usando `gabi.hoje.BRT`).
- [ ] **Step 4: Rodar** `pytest tests/teams tests/test_esquema.py tests/test_db.py -q` → verde.
- [ ] **Step 5: Commit** `feat(teams): tabelas e regra das 2 horas úteis`.

---

### Task 5: Coletor

**Files:**
- Create: `gabi/teams/coletar.py`, `gabi/teams/__main__.py`, `gabi/teams/fontes.py`
- Test: `tests/teams/test_coletar.py`, `tests/teams/test_main.py`

**Interfaces:**
- Consumes: `PonteGraph.teams_chats/teams_mensagens` (Task 3), tabelas e `regra.py` (Task 4), `gabi.rodada.registrar_rodada` (como `gabi/agenda/__main__.py`).
- Produces:
  - `fontes.listar(con) -> list[dict]`, `fontes.criar(con, conta) -> int` (conta validada por `gabi.fontes.google_oauth.conta_valida`; sempre `a_decidir`; duplicada → `ErroFonte(conflito=True)`), `fontes.definir_estado(con, fonte_id, estado)`, `ErroFonte` com os mesmos atributos de `gabi.agenda.fontes.ErroFonte`.
  - `coletar.coletar(con, ponte, agora: dt.datetime) -> dict[str, dict]` por conta liberada (`estado='sim'`): `{"chats": n, "novas": n}` ou `{"erro": str}`.
  - Regra por chat: pula se `ultima_em` ≤ cursor; sem cursor lê só os últimos 24 h (`teams.janela_inicial_horas`, padrão 24); para cada mensagem: `de_eu` → `minha_ultima_resposta_em = max(...)`; não `de_eu` e (`tipo == 'um_a_um'` ou `mencoes_eu`) → `ultima_para_mim_em = max(...)` e `de_nome`; o cursor avança sempre.
  - `__main__.main(banco=None, *, ponte=None) -> int`: imprime **só contagens**; rodada `teams` ok mesmo sem conta liberada; sai 1 só se todas as contas falham.

- [ ] **Step 1: Testes que falham** em `test_coletar.py`: `test_um_a_um_vira_pendente`, `test_grupo_sem_mencao_nao_vira_pendente`, `test_grupo_com_mencao_vira_pendente`, `test_minha_resposta_registra_resposta`, `test_primeira_coleta_ignora_historico_antigo`, `test_cursor_evita_reler`, `test_chat_com_403_e_pulado_e_conta_segue`, `test_429_encerra_a_conta_sem_derrubar_a_outra`, `test_conta_nao_liberada_nao_e_lida`, `test_nenhum_texto_em_banco_nem_saida` (fixture com `de_nome="Ana"`: o único texto livre persistido é `de_nome`; varrer todas as colunas e o `capsys`); em `test_main.py`: `test_saida_so_contagens`, `test_sem_socket_retorna_2`, `test_sem_fonte_configurada_retorna_2`.
- [ ] **Step 2: Rodar** `pytest tests/teams -q` → falha.
- [ ] **Step 3: Implementar** `fontes.py`, `coletar.py` e `__main__.py` seguindo `gabi/agenda/fontes.py` e `gabi/agenda/__main__.py`; `ErroGraphNess` de um chat com status 403/404 pula o chat; 429 (`_ErroStatus.status`) encerra a conta; demais erros vão para `teams_fonte.ultimo_erro` (mensagem já sem corpo).
- [ ] **Step 4: Rodar** `pytest tests/teams -q` → verde.
- [ ] **Step 5: Commit** `feat(teams): coletor das conversas (sem texto)`.

---

### Task 6: Aviso `teams_sem_resposta`

**Files:**
- Modify: `gabi/avisos.py` (`gerar_avisos`, `revalidar`, `TIPOS_REVALIDADOS`), `gabi/rotas/avisos.py` (`descrever`)
- Test: `tests/test_avisos.py` (ou novo `tests/test_avisos_teams.py` com a mesma fixture `con`)

**Interfaces:**
- Consumes: `regra.pendente`, `regra.ler_config`, tabela `teams_conversa` (Task 4).
- Produces: aviso `tipo="teams_sem_resposta"`, `chave=f"{conta}|{chat_id}"`, `payload={"chave", "conta", "chat_id", "tipo_chat", "de_nome", "desde"}` (sem texto). Ao criar, grava `teams_conversa.ultimo_aviso_em = agora`. `revalidar` devolve `RESOLVIDO` se `minha_ultima_resposta_em >= ultima_para_mim_em` (ou a linha sumiu), senão `VALE`. `descrever` → título `"Teams: {de_nome} te chamou"` (1:1) ou `"Teams: {de_nome} te mencionou"` (grupo), texto `"sem resposta desde {dd/mm HH:MM} ({conta})"` em horário de Brasília. `teams_sem_resposta` **não** entra em `SEMANAL`.

- [ ] **Step 1: Testes que falham**: `test_teams_um_a_um_depois_de_2h_uteis_gera_aviso`, `test_teams_antes_de_2h_uteis_nao_gera`, `test_teams_grupo_sem_mencao_nao_gera`, `test_teams_respondi_antes_do_envio_e_resolvido` (via `triar`: estado `resolvido` e aviso fechado sem envio), `test_teams_nao_repete_para_a_mesma_mensagem`, `test_teams_mensagem_nova_depois_do_aviso_gera_outro_no_dia_seguinte`, `test_teams_payload_sem_texto` (chaves ⊂ lista fixa), `test_descrever_teams_um_a_um_e_mencao`.
- [ ] **Step 2: Rodar** → falha.
- [ ] **Step 3: Implementar** `_teams_sem_resposta(con, agora, novo)` (chamado em `gerar_avisos` após `_hermes_parado`), a ramificação em `revalidar`, a inclusão em `TIPOS_REVALIDADOS` e o `descrever`.
- [ ] **Step 4: Rodar** `pytest tests/test_avisos.py tests/test_avisos_antecipados.py tests/test_telegram.py tests/rotas -q` → verde (o Telegram usa `descrever` e `triar`, sem mudar).
- [ ] **Step 5: Commit** `feat(avisos): Teams sem resposta há 2 horas úteis`.

---

### Task 7: API de cadastro e docs

**Files:**
- Create: `gabi/rotas/teams.py`
- Modify: `gabi/api.py` (registrar o router, como `rotas_agenda`), `docs/api.md` e `docs/openapi.json` (regerar com `tools.gerar_docs_api`)
- Test: `tests/rotas/test_teams.py`

**Interfaces:**
- Consumes: `gabi.teams.fontes` (Task 5).
- Produces: `GET /api/v1/teams/fontes` (envelope `{"fontes": [...]}`), `POST /api/v1/teams/fontes` `{conta}` → 201 `{id}`, `PUT /api/v1/teams/fontes/{id}/estado` `{estado}`; só o `boss` (`exigir("boss")`); auditoria com ids, nunca valores; erros no padrão de `gabi/rotas/agenda.py` (400/404/409).

- [ ] **Step 1: Testes que falham**: `test_lista_vazia`, `test_criar_a_decidir`, `test_conta_invalida_400`, `test_duplicada_409`, `test_estado_invalido_400`, `test_estado_inexistente_404`, `test_so_boss`; ajustar `tests/test_matriz_acesso.py` se ele enumerar rotas.
- [ ] **Step 2: Rodar** → falha.
- [ ] **Step 3: Implementar** o router copiando a estrutura de `gabi/rotas/agenda.py` (rotas `/fontes`); regerar a doc com o comando de `tools.gerar_docs_api`.
- [ ] **Step 4: Rodar** `pytest tests/rotas tests/test_docs_api.py tests/test_matriz_acesso.py -q` → verde.
- [ ] **Step 5: Commit** `feat(api): cadastro das contas de Teams`.

---

### Task 8: Unidades systemd e documentação

**Files:**
- Create: `deploy/gabi-brain-teams.service`, `deploy/gabi-brain-teams.timer`
- Modify: `deploy/instalar.sh` (instalar as duas units, sem `enable`), `tests/test_deploy.py`, `docs/fontes/graph-ness.md`, `docs/adr/019-graph-ness.md` (seção Teams), `docs/runbook.md` (`#graph-ness`, passo 7 = Teams), `docs/STATUS.md`, `docs/BACKLOG.md`

**Interfaces:**
- Produces: serviço oneshot idêntico ao do correio (`-m gabi.teams`, `GABI_FONTES_SOCKET`, `RestrictAddressFamilies=AF_UNIX`), timer `OnCalendar=*-*-* 07..20:00,05,10,15,20,25,30,35,40,45,50,55:00 America/Sao_Paulo`, `Persistent=true`, **não habilitado**.

- [ ] **Step 1: Teste que falha** em `tests/test_deploy.py` seguindo `test_unidades_do_correio_seguem_o_padrao_e_nao_sao_habilitadas` (`test_unidades_do_teams_seguem_o_padrao_e_nao_sao_habilitadas`).
- [ ] **Step 2: Rodar** → falha.
- [ ] **Step 3: Escrever** as units a partir de `deploy/gabi-brain-correio.*`, acrescentar ao `instalar.sh` junto ao correio com o comentário "instalado e DESLIGADO (liga quando houver conta de Teams liberada)", e atualizar os docs: passos do dono (cadastrar a conta via `POST /api/v1/teams/fontes`/painel, liberar `sim`, `systemctl enable --now gabi-brain-teams.timer`), a ressalva de que as permissões de aplicativo alcançam o tenant todo e a trava está no código, e que ionic/canais/modelo/responder ficam para depois.
- [ ] **Step 4: Rodar** `pytest tests/test_deploy.py -q` → verde.
- [ ] **Step 5: Commit** `feat(deploy): timer do Teams (desligado) e docs`.

---

### Task 9: Cadastro no painel e suíte completa

**Files:**
- Create: `painel/src/telas/CadastrosTeams.tsx`
- Modify: `painel/src/navegacao.ts`, `painel/src/App.tsx` (rota/aba ao lado de Agenda), `painel/tests/` (teste no padrão do de CadastrosAgenda)

**Interfaces:**
- Consumes: `GET/POST /api/v1/teams/fontes`, `PUT /api/v1/teams/fontes/{id}/estado` (Task 7).
- Produces: tela com lista (conta, estado, última coleta, último erro) e botões Liberar/Pausar, mais campo de nova conta; copiar `CadastrosAgenda.tsx` e remover o que for de calendário.

- [ ] **Step 1: Teste do painel que falha** (padrão de `painel/tests` para CadastrosAgenda): lista as contas, cria, muda o estado.
- [ ] **Step 2: Rodar** o teste do painel → falha.
- [ ] **Step 3: Implementar** a tela e ligar na navegação; `npm run build` (o build vai para `gabi/static`/`painel/dist` como nas outras entregas).
- [ ] **Step 4: Suíte completa** em shards (`scratchpad/suite_paralela.sh` ou o procedimento de `docs/historico/PROGRESSO-GOAL.md`) e ler o resumo do pytest (não confiar no exit code do pipeline): esperado 0 falhas.
- [ ] **Step 5: Commit** `feat(painel): cadastro das contas de Teams`.

---

## Fora deste plano

Ionic (depende do administrador), menção em canais (fase 1b), classificação pelo modelo (fase 2, gate `teams.classificar`), responder pelo Teams (exige ADR de exceção à R2), ligar o timer, merge da branch.
