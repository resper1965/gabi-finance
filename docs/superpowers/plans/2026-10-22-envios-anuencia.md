# Envios com anuência (AT1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Hermes propõe evento de agenda (ness/bekaa/gmail) ou mensagem no Teams da ness; o envio só sai quando o Ricardo clica Enviar no painel.

**Architecture:** Domínio puro em `gabi/envios/` (fila `envio_proposta`, validação, resolução, ciclo de vida, executor). A rede fica só no serviço de fontes: métodos novos em `google_agenda.py` e num arquivo novo `graph_ness_envios.py`, liberados na lista branca da ponte. O MCP ganha 2 ferramentas que só propõem; a API ganha `/api/v1/envios` (listar, enviar, recusar); o painel ganha a área Envios.

**Tech Stack:** Python 3 + SQLite (stdlib `sqlite3`), FastAPI, MCP (`mcp.server.mcpserver`), React + Vite + vitest. Testes: `.venv/bin/python -m pytest -q`; painel `cd painel && npx vitest run && npm run build`.

**Spec:** `docs/superpowers/specs/2026-10-22-envios-anuencia-design.md` · ADR `docs/adr/024-envios-com-anuencia.md`

## Global Constraints
- Nenhum título, texto, nome ou e-mail em log, stderr, `decisao` ou mensagem de erro de provedor; motivos de falha são códigos fixos.
- Interruptor `parametro envios.escrita`: só o valor JSON `"ligado"` liga; ausente/qualquer outro = desligado.
- `parametro envios.contas_agenda`: lista JSON de contas; padrão `[]`. `parametro painel.url`: texto; padrão ausente.
- Validade: `vence_em = min(criada + 24h, inicio_utc do evento)`.
- `chave` = 26 caracteres base32hex minúsculos (`base64.b32hexencode(secrets.token_bytes(16)).decode().lower().rstrip("=")`).
- `conteudo` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; `hash` = sha256 hex desse texto.
- Fuso de entrada e exibição: `America/Sao_Paulo`; armazenamento em UTC `YYYY-MM-DDTHH:MM:SSZ`.
- Limites: título 1–200, `duracao_min` 5–720, convidados 1–30, texto do Teams 1–4000, descrição ≤ 2000.
- Esquema novo = migração `0076`. Código e comentários em pt-BR, no estilo dos arquivos vizinhos (docstring de módulo com "Consome:").
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nada de push, merge ou instalação.

## Review Focus
1. `inicio` com fuso explícito diferente (`...Z`, `+00:00`) deve ser convertido certo; sem fuso = Brasília (teste na Task 1).
2. Convidado e-mail com maiúsculas/espaços/repetido: normaliza para minúsculo, sem duplicar (Task 1).
3. Nome com/sem acento ("Joao" × "João Silva" cadastrado como "João Silva"): casa ignorando caixa e acento, por igualdade do nome inteiro (Task 1).
4. Texto do Teams com `<b>`/`&`: sai como `contentType: "text"`, sem escapar nem interpretar (Task 4).
5. Enviar uma proposta criada com a escrita desligada, depois de ligar: funciona normalmente, porque a checagem é na hora do envio (Task 6).

---

### Task 1: Migração 0076 e criação de propostas

**Files:**
- Create: `migrations/0076_envio_proposta.sql`, `gabi/envios/__init__.py`, `gabi/envios/propostas.py`
- Test: `tests/envios/__init__.py`, `tests/envios/test_propostas.py`

**Interfaces:**
- Produces:
  - `class ErroEnvio(Exception)` com `codigo: str`, `mensagem: str`, `candidatos: list[dict] | None`.
  - `escrita_ligada(con) -> bool`; `contas_agenda(con) -> list[str]` (minúsculas); `provedor_da_conta(con, conta) -> str | None` (de `agenda_fonte` com `calendario_id='primary'`).
  - `contas_teams(con) -> list[str]` (`teams_fonte.estado='sim'`).
  - `resolver_convidados(con, itens: list[str]) -> list[str]`. Levanta `ErroEnvio("convidado_ambiguo", ..., candidatos=[{"nome","email"}])` ou `ErroEnvio("convidado_invalido")`.
  - `resolver_chat(con, conta, nome) -> dict` (`{"chat_id","destino_nome"}`). Levanta `ErroEnvio("destino_ambiguo", candidatos=[{"nome","tipo"}])`.
  - `criar_evento(con, agora: datetime, *, conta, titulo, inicio, duracao_min, convidados, descricao="", online=True) -> dict`.
  - `criar_teams_chat(con, agora, *, conta, chat_com, texto) -> dict`.
  - `criar_teams_canal(con, agora, *, conta, equipe_id, canal_id, equipe_nome, canal_nome, texto) -> dict`.
  - Todas as três retornam `{"id", "estado": "pendente", "resumo": str, "vence_em"}`.
  - `normalizar_nome(s) -> str` (casefold sem acento, espaços colapsados).

- [ ] **Step 1: Migração.** `envio_proposta` com as colunas da spec (tabela "Modelo de dados"), `check` em `tipo in ('evento','teams_chat','teams_canal')` e `estado in ('pendente','enviando','enviada','recusada','falhou','incerto','vencida')`, `chave text not null unique`, `criada_em` default `strftime('%Y-%m-%dT%H:%M:%SZ','now')`, `vence_em text not null`, índice `envio_proposta_estado(estado)`. Cabeçalho no estilo das outras (`-- 0076: ...`, linha "Desfazer: drop table envio_proposta.").
- [ ] **Step 2: Testes que falham** em `tests/envios/test_propostas.py`, usando o banco da `conftest` (veja `tests/rotas/test_contatos.py` para a fixture de conexão migrada):
  - `test_criar_evento_grava_conteudo_canonico_hash_e_chave`: com `envios.contas_agenda=["resper@ness.com.br"]` e `agenda_fonte(conta='resper@ness.com.br', provedor='graph', calendario_id='primary', estado='sim')`, `criar_evento(..., inicio="2026-10-23T15:00", duracao_min=60, convidados=["Ana@X.com "," ana@x.com"])` grava uma linha `pendente`, `json.loads(conteudo)` == `{"conta":"resper@ness.com.br","provedor":"graph","titulo":...,"inicio_utc":"2026-10-23T18:00:00Z","fim_utc":"2026-10-23T19:00:00Z","fuso":"America/Sao_Paulo","convidados":["ana@x.com"],"descricao":"","online":True}`, `hash == sha256(conteudo)`, `re.fullmatch(r"[0-9a-v]{26}", chave)`.
  - `test_inicio_com_fuso_explicito_converte` (`"2026-10-23T18:00:00Z"` → `inicio_utc "2026-10-23T18:00:00Z"`).
  - `test_vence_em_e_o_menor_entre_24h_e_inicio` (início em 3 h → `vence_em` = início; em 3 dias → criada + 24h).
  - `test_inicio_no_passado_recusado` → `ErroEnvio.codigo == "inicio_passado"`.
  - `test_conta_fora_da_lista_recusada` → `"conta_nao_permitida"`; idem conta na lista sem `agenda_fonte`.
  - `test_limites` (título vazio/201, duração 4/721, 0 e 31 convidados, descrição 2001) → `"requisicao_invalida"`.
  - `test_convidado_por_nome_ignora_acento_e_caixa`: `contato_google(conta,'+5511…','João Silva')` + `contato_google_email(conta,'joao@x.com', telefone)` → `resolver_convidados(con, ["joao silva"]) == ["joao@x.com"]`.
  - `test_convidado_ambiguo_lista_candidatos`: dois e-mails para o mesmo nome → `codigo "convidado_ambiguo"` e `candidatos` com os 2; nada gravado.
  - `test_convidado_sem_contato` → `"convidado_ambiguo"` com `candidatos == []`.
  - `test_criar_teams_chat_resolve_por_de_nome`: `teams_fonte(conta, estado='sim')` + `teams_conversa(conta, 'c1', 'um_a_um', 'Ana Souza')` → conteúdo `{"conta","chat_id":"c1","destino_nome":"Ana Souza","texto"}`, `vence_em` = criada + 24h; dois chats "Ana Souza" → `"destino_ambiguo"`; conta com `teams_fonte.estado='nao'` → `"conta_nao_permitida"`.
  - `test_criar_teams_canal_grava_ids_e_nomes`.
  - `test_texto_teams_limites` (vazio, 4001).
- [ ] **Step 3: Rodar** `.venv/bin/python -m pytest tests/envios -q`. Esperado: falha (módulo inexistente).
- [ ] **Step 4: Implementar** `gabi/envios/propostas.py`. Ler `parametro` como em `gabi/contatos/contatos.py::_parametro`. A busca por nome compara `normalizar_nome` do nome inteiro com `contato_google.nome`, junta `contato_google_email` por `(conta, telefone)` e deduplica os e-mails. O resumo é em pt-BR curto, por exemplo `"Evento 'X' qui 23/10 15:00–16:00 (ness), 2 convidados"` ou `"Teams: chat com Ana Souza"`.
- [ ] **Step 5: Rodar** `.venv/bin/python -m pytest tests/envios tests/test_esquema.py tests/test_db.py -q`. Esperado: passa. Se o teste de esquema fixa a lista de tabelas ou migrações, atualize-o.
- [ ] **Step 6: Commit** `feat(envios): fila envio_proposta e criação de propostas (0076)`.

### Task 2: Ciclo de vida (listar, vencer, recusar, reservar, concluir)

**Files:**
- Modify: `gabi/envios/propostas.py`
- Test: `tests/envios/test_ciclo.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `listar(con, agora, estado="pendente") -> list[dict]`. Antes de listar, marca como `vencida` as pendentes com `vence_em <= agora`. Cada item vem como `{id, tipo, conta, conteudo: dict, hash, estado, motivo, criada_em, vence_em, decidida_em, enviada_em}`. Com `estado="decididas"`, traz as 20 mais recentes não pendentes, por `decidida_em desc`.
  - `recusar(con, id, quem, agora) -> None`. Levanta `ErroEnvio("nao_encontrado")` ou `ErroEnvio("conflito")`.
  - `reservar(con, id, hash, quem, agora) -> dict`. Devolve a linha e faz a transição atômica `pendente → enviando`. A ordem das checagens é: `nao_encontrado` → vencida (marca `vencida` e levanta `"vencida"`) → `conflito` (estado ≠ pendente) → `"hash_diferente"` → `"envios_desligados"` → conta ainda permitida (se não, grava `falhou`/`conta_nao_permitida` e levanta `"conta_nao_permitida"`) → `update ... where id=? and estado='pendente'`, e rowcount 0 levanta `"conflito"`.
  - `concluir(con, id, estado, *, motivo=None, externo_id=None, agora) -> None`, com estado em `enviada`, `falhou` ou `incerto`.
  - `auditar(con, quem, agora, texto)`: insere em `decisao` com origem `'envios'`. O texto só leva id, tipo, conta e estado.

- [ ] **Step 1: Testes que falham:**
  - `test_listar_marca_vencidas`.
  - `test_recusar_so_pendente`, com 409 equivalente `conflito` na segunda vez.
  - `test_reservar_hash_diferente`.
  - `test_reservar_desligado_nao_muda_estado` (continua `pendente`).
  - `test_reservar_duas_vezes_segunda_e_conflito`.
  - `test_reservar_conta_removida_da_lista_vira_falhou`.
  - `test_auditoria_sem_conteudo`: o texto de `decisao` não contém título, e-mail nem texto.
  - `test_ligar_depois_de_criar_permite_enviar` (Review Focus 5).
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar.** Toda escrita de estado vai com `transacao(con)` de `gabi.db`, e a auditoria entra na mesma transação da decisão.
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/envios -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(envios): ciclo de vida da proposta`.

### Task 3: Google, criar evento

**Files:**
- Modify: `gabi/fontes/google_agenda.py`, `gabi/fontes/ponte.py` (PERMITIDOS `google_agenda` + `PonteAgenda.evento_criar`), `tools/obter_token_google.py` (ESCOPOS ganha `https://www.googleapis.com/auth/calendar.events`, mantendo os atuais), `gabi/fontes/google_oauth.py` (docstring dos escopos)
- Test: `tests/fontes/test_google_agenda.py`, `tests/fontes/test_ponte.py`, `tests/test_obter_token_google.py`

**Interfaces:**
- Produces: `GoogleAgenda.evento_criar(conta: str, chave: str, evento: dict) -> dict` (`{"externo_id": str, "ja_existia": bool}`); `PonteAgenda.evento_criar(...)` com a mesma assinatura, que valida a forma da resposta (`ErroGoogleOAuth("resposta inválida do serviço de fontes")`). O `evento` é o `conteudo` da Task 1.

- [ ] **Step 1: Testes que falham:**
  - `test_evento_criar_post_com_id_sendupdates_e_meet`: um único POST para `https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all&conferenceDataVersion=1`. O corpo é `{"id": chave, "summary", "description", "start": {"dateTime": inicio_utc, "timeZone": "America/Sao_Paulo"}, "end": {...}, "attendees": [{"email": e}...], "conferenceData": {"createRequest": {"requestId": chave, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}`. A resposta `200 {"id": chave}` devolve `{"externo_id": chave, "ja_existia": False}`.
  - `test_evento_criar_sem_online_nao_pede_conferencia` (sem `conferenceDataVersion` e sem `conferenceData`).
  - `test_evento_criar_409_e_ja_existia` → `{"externo_id": chave, "ja_existia": True}`.
  - `test_evento_criar_4xx_levanta_com_status`: um 403 levanta `ErroGoogleOAuth` com mensagem exatamente `"calendar.events.insert -> 403"`.
  - `test_evento_criar_chave_invalida` (fora de `[0-9a-v]{5,1024}`) levanta antes de qualquer HTTP.
  - `test_evento_criar_401_renova_token_uma_vez`.
  - Na ponte: `google_agenda` permite `evento_criar`.
  - No `obter_token_google`: `calendar.events` está nos escopos.
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar** com `chamar`/`_pegar` no estilo existente, criando um `_postar` análogo ao `_pegar` com a mesma renovação em 401. Atualizar a docstring do módulo: deixa de ser "SÓ leitura" e passa a ser "leitura + criar evento aprovado (ADR-024)".
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/fontes tests/test_obter_token_google.py -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(fontes): criar evento no Google com chave de idempotência`.

### Task 4: Graph da ness, evento e Teams delegado

**Files:**
- Create: `gabi/fontes/graph_ness_envios.py`
- Modify: `gabi/fontes/graph_ness.py` (métodos de `GraphNess` que delegam, como os de contatos; o construtor aceita `token_teams=None`; `graph_ness_do_ambiente` monta `TokenDelegado` quando existe `GRAPH_NESS_TEAMS_REFRESH`), `gabi/fontes/ponte.py` (PERMITIDOS `graph_ness` + métodos de `PonteGraph`)
- Test: `tests/fontes/test_graph_ness_envios.py`, `tests/fontes/test_ponte.py`

**Interfaces:**
- Produces:
  - Em `graph_ness_envios`: `class TokenDelegado(tenant, client_id, refresh, conta_esperada, http=_http_real, agora=time.time)` com `__call__() -> str`, `invalidar()` e `__repr__` oculto. A troca é `POST {LOGIN}/{tenant}/oauth2/v2.0/token`, `grant_type=refresh_token`, sem secret, com o scope `"https://graph.microsoft.com/ChatMessage.Send https://graph.microsoft.com/ChannelMessage.Send https://graph.microsoft.com/Team.ReadBasic.All https://graph.microsoft.com/Channel.ReadBasic.All offline_access"`. Guarda em memória o `refresh_token` novo, se vier. Na primeira troca confere `GET /me` (`userPrincipalName` minúsculo igual a `conta_esperada`); se não bater, `ErroGraphNess("login_teams_conta_diferente")`. Status 400 ou 401 na troca dá `ErroGraphNess("login_teams_expirado")`.
  - `evento_criar(fonte, conta, chave, evento) -> {"externo_id"}`: `POST /users/{conta}/events` com o token de app, corpo `{"subject","body":{"contentType":"text","content":descricao},"start":{"dateTime":inicio_utc sem Z,"timeZone":"UTC"},"end":{...},"attendees":[{"emailAddress":{"address":e},"type":"required"}],"transactionId":chave}` e, se `online`, `"isOnlineMeeting":true,"onlineMeetingProvider":"teamsForBusiness"`.
  - `teams_equipes(fonte, conta) -> [{"id","nome"}]` (`/me/joinedTeams`, delegado).
  - `teams_canais(fonte, conta, equipe_id) -> [{"id","nome"}]` (`/teams/{id}/channels`).
  - `teams_chat_enviar(fonte, conta, chat_id, texto) -> {"externo_id"}` (`POST /chats/{id}/messages`).
  - `teams_canal_enviar(fonte, conta, equipe_id, canal_id, texto) -> {"externo_id"}` (`POST /teams/{e}/channels/{c}/messages`). As duas mandam o corpo `{"body":{"contentType":"text","content":texto}}`.
  - Erros HTTP dão `ErroGraphNess(f"{operacao} -> {status}")`. Conta fora de `fonte.contas()` dá `ErroGraphNess("conta não autorizada")`. Sem token delegado, `ErroGraphNess("teams_sem_login")`.
  - Os métodos `GraphNess.evento_criar` / `teams_equipes` / `teams_canais` / `teams_chat_enviar` / `teams_canal_enviar` existem em `GraphNess` e `PonteGraph` com as mesmas assinaturas, sem o `fonte`.

- [ ] **Step 1: Testes que falham** (reusar `TokenFalso` e `_graph` de `tests/fontes/test_graph_ness.py`, estendendo `_graph` para aceitar um token delegado falso):
  - Corpo e URL exatos de cada POST.
  - `test_teams_texto_com_html_vai_como_text` (`"<b>oi</b> & tchau"` vai intacto e `contentType == "text"`).
  - `test_conta_fora_da_lista`.
  - `test_sem_login_teams`.
  - `test_token_delegado_expirado` (400 → `login_teams_expirado`).
  - `test_token_delegado_conta_diferente`.
  - `test_token_delegado_guarda_refresh_rotacionado_em_memoria`.
  - `test_repr_oculto`.
  - **Varredura** `test_envios_so_tem_os_verbos_e_urls_previstos`: lê o fonte de `graph_ness_envios.py` e confere que os únicos literais de método HTTP são `"GET"` e `"POST"` e que não aparecem `/sendMail`, `/reply`, `/forward`, `DELETE`, `PATCH` nem `/chats"` (criar chat).
  - Conferir que `tests/fontes/test_graph_ness.py` (a varredura existente de `graph_ness.py`) continua passando sem afrouxar nada.
  - Na ponte, os 5 nomes novos estão em `PERMITIDOS["graph_ness"]`, e `PonteGraph` valida a forma das respostas.
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar.** O delegado usa as mesmas `M365_TENANT_ID`/`M365_CLIENT_ID` e o refresh de `GRAPH_NESS_TEAMS_REFRESH`. `conta_esperada` é a primeira de `M365_CONTAS`.
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/fontes -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(fontes): evento e Teams (delegado) na ness, em arquivo separado`.

### Task 5: Ferramenta de login delegado do Teams

**Files:**
- Create: `tools/obter_token_teams.py`
- Test: `tests/test_obter_token_teams.py`

**Interfaces:**
- Produces: CLI `sudo .venv/bin/python -m tools.obter_token_teams --env /etc/gabi/graph-ness.env [--gravar]`. Faz o fluxo de código de dispositivo: `POST {LOGIN}/{tenant}/oauth2/v2.0/devicecode` com os escopos da Task 4, mostra `verification_uri` e `user_code`, e faz polling em `/token` com `grant_type=urn:ietf:params:oauth:grant-type:device_code` respeitando `interval` e `authorization_pending`/`slow_down`. Com `--gravar`, escreve ou substitui `GRAPH_NESS_TEAMS_REFRESH=` no env sem mostrar o token; sem `--gravar`, imprime só a linha final. Lê tenant e client id do mesmo env. Funções puras testáveis: `pedir_codigo(http, tenant, client_id) -> dict`, `esperar_token(http, tenant, client_id, device_code, intervalo, dormir) -> str`, `gravar_no_env(caminho, valor)` (preserva as outras linhas e o modo 0600).

- [ ] **Step 1: Testes que falham:**
  - `pending → pending → ok` devolve o refresh.
  - `slow_down` aumenta o intervalo em 5 s.
  - `expired_token` levanta `SystemExit` com mensagem sem segredo.
  - `gravar_no_env` substitui a linha existente e preserva as outras e o modo.
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar** no estilo de `tools/obter_token_google.py`: docstring com o uso e nada gravado sem `--gravar`.
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/test_obter_token_teams.py -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(tools): login delegado do Teams por código de dispositivo`.

### Task 6: Executor do envio

**Files:**
- Create: `gabi/envios/enviar.py`
- Test: `tests/envios/test_enviar.py`

**Interfaces:**
- Consumes: Task 2 (`reservar`, `concluir`, `auditar`) e os métodos de ponte das Tasks 3 e 4.
- Produces: `enviar(con, proposta_id: int, hash: str, quem: str, agora, google, graph) -> dict` (`{"id", "estado", "motivo"?}`). `google` é um objeto com `evento_criar`, ou None; `graph` é um objeto com `evento_criar`, `teams_chat_enviar` e `teams_canal_enviar`, ou None. Propaga o `ErroEnvio` de `reservar`. Depois de reservar:
  - O provedor vem de `conteudo.provedor` (evento) ou é o Graph (Teams). Provedor None conclui `falhou`/`fonte_indisponivel`.
  - Sucesso conclui `enviada` com `externo_id`.
  - Exceção cuja mensagem casa `r"-> (\d{3})$"` conclui `falhou`/`provedor_<status>`.
  - Mensagens `login_teams_expirado`, `teams_sem_login`, `login_teams_conta_diferente` e `conta não autorizada` concluem `falhou` com esse código (`conta não autorizada` vira `conta_nao_permitida`).
  - Qualquer outra exceção (timeout, "serviço de fontes indisponível") conclui `incerto`/`sem_confirmacao`.
  - Audita `"envios: proposta {id} ({tipo}, {conta}) → {estado}"` em todos os casos. Não há nenhuma repetição.
  - Uma trava `flock` não bloqueante em `<pasta do banco>/locks/envios.lock` (mesmo padrão de `contatos_gravar.trava`) protege a chamada inteira; trava ocupada levanta `ErroEnvio("conflito")` antes de reservar.

- [ ] **Step 1: Testes que falham** (provedores falsos que registram chamadas):
  - `test_evento_google_ok`.
  - `test_evento_graph_ok`.
  - `test_teams_chat_ok`.
  - `test_teams_canal_ok`.
  - `test_google_403_falhou_provedor_403`.
  - `test_timeout_teams_incerto_uma_chamada` (exceção genérica → `incerto` e exatamente 1 chamada).
  - `test_login_expirado_motivo_fixo`.
  - `test_provedor_ausente`.
  - `test_desligado_nao_chama_provedor` (0 chamadas).
  - `test_duas_chamadas_seguidas_um_envio`.
  - `test_auditoria_e_stderr_sem_conteudo` (`capsys`: nenhum título ou texto em stdout/stderr).
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/envios -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(envios): executor com uma tentativa e estado incerto`.

### Task 7: Rotas da API `/api/v1/envios`

**Files:**
- Create: `gabi/rotas/envios.py`
- Modify: `gabi/api.py` (`include_router`), `docs/openapi.json` e `docs/api.md` (regerar com `tools/gerar_docs_api.py`), `tests/test_matriz_acesso.py` se ele lista as rotas
- Test: `tests/rotas/test_envios.py`

**Interfaces:**
- Consumes: Tasks 2 e 6. As fontes vêm de `request.app.state.fontes.get("google_agenda")` e `.get("graph_ness")` (fábricas; chame e use None se ausente).
- Produces:
  - `GET /api/v1/envios?estado=pendente|decididas` → envelope `{"itens": [...], "escrita": "ligado"|"desligado"}`.
  - `POST /api/v1/envios/{id}/enviar` com corpo `{"hash": str}` → envelope `{"id","estado","motivo"?}`.
  - `POST /api/v1/envios/{id}/recusar` → `{"id","estado":"recusada"}`.
  - Mapeamento de `ErroEnvio`: `nao_encontrado` → 404; `conflito`, `vencida`, `hash_diferente`, `envios_desligados` e `conta_nao_permitida` → 409, com o código como `erro`; o resto → 400 `requisicao_invalida`. Use `erro`, `_con`, `_corpo`, `_json` e `_agora` de `gabi.rotas.dinheiro`, como em `rotas/contatos.py`. Só `boss`.

- [ ] **Step 1: Testes que falham** (no padrão de `tests/rotas/test_contatos.py`, com fontes falsas injetadas na app):
  - Listar pendentes com o `conteudo` legível e `escrita`.
  - Enviar ok.
  - `hash` ausente → 400.
  - `hash` errado → 409 `hash_diferente`.
  - Desligado → 409 `envios_desligados`, com 0 chamadas ao falso.
  - Recusar.
  - 404.
  - Não boss → 403.
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar e regerar os docs.**
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/rotas tests/test_docs_api.py tests/test_matriz_acesso.py tests/test_api.py -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(api): rotas de envios (listar, enviar, recusar)`.

### Task 8: Ferramentas MCP `propor_evento` e `propor_teams`

**Files:**
- Create: `gabi/mcp/ferramentas_envios.py`
- Modify: `gabi/mcp/servidor.py` (`ESCOPOS_FERRAMENTAS` += `ferramentas_envios.ESCOPOS`; `ESCOPOS_HERMES` += `"envios"`; `criar_mcp(..., graph=None)` repassado a `ferramentas_envios.registrar(srv, executar, graph)`; a fábrica do serviço monta `PonteGraph(caminho)` quando há socket), `gabi/mcp/tokens.py` (`ESCOPOS` += `"envios"`), `tests/mcp/test_servidor.py` (18 → 20 ferramentas, com os nomes), `docs/fontes/hermes.md` (`python -m tools.gerar_hermes`)
- Test: `tests/mcp/test_envios.py`

**Interfaces:**
- Consumes: Task 1 (`criar_*`, `resolver_*`, `ErroEnvio`, `contas_teams`) e `PonteGraph.teams_equipes/teams_canais` (Task 4).
- Produces:
  - `propor_evento(conta: str, titulo: str, inicio: str, duracao_min: int, convidados: list[str], descricao: str = "", online: bool = True) -> dict`.
  - `propor_teams(texto: str, chat_com: str = "", equipe: str = "", canal: str = "") -> dict`. A conta é a única de `contas_teams`; se houver 0 ou mais de 1, devolve `ErroFerramenta("conta_nao_permitida")`. Exige exatamente um destino: `chat_com`, ou `equipe` + `canal`. Equipe e canal são resolvidos por `normalizar_nome` igual na lista viva; 0 ou mais de 1 resultado dá `destino_ambiguo` com candidatos (só os nomes). `graph` None dá `fonte_indisponivel`.
  - As docstrings dizem: "PROPÕE … o envio só sai quando o Ricardo clica Enviar no painel".
  - O retorno inclui `link = painel.url + "#envios"` quando o parâmetro existe.
  - `ErroEnvio` vira `ErroFerramenta(codigo, mensagem)`. Os candidatos entram na mensagem ou num campo extra, no padrão usado por `executar` (ver como `ErroFerramenta` é serializado em `servidor.py`; se ele não aceita campos extras, inclua os candidatos na mensagem como `"nome <email>"` separados por `; `).

- [ ] **Step 1: Testes que falham:**
  - Cada ferramenta cria a proposta pendente.
  - Sem escopo `envios` → `sem_escopo`.
  - Ambiguidade devolve os candidatos.
  - `propor_teams` com dois destinos → `requisicao_invalida`.
  - `test_nenhuma_ferramenta_aprova_ou_envia`: nenhum nome de ferramenta contém `enviar`, `aprovar` ou `confirmar`.
  - Lista exata das 20 ferramentas.
  - `test_hermes` continua conferindo `docs/fontes/hermes.md` contra `ferramentas_do_token(ESCOPOS_HERMES)`.
- [ ] **Step 2: Rodar.** Esperado: falha.
- [ ] **Step 3: Implementar e regerar** `docs/fontes/hermes.md`.
- [ ] **Step 4: Rodar** `.venv/bin/python -m pytest tests/mcp -q`. Esperado: passa.
- [ ] **Step 5: Commit** `feat(mcp): propor_evento e propor_teams (só propõem)`.

### Task 9: Painel, área Envios

**Files:**
- Create: `painel/src/telas/Envios.tsx`
- Modify: `painel/src/navegacao.ts` (grupo "Dia" ganha `{ id: "envios", rotulo: "Envios", pergunta: "O que espera meu OK para sair?", abas: [["envios", "Envios", "O que espera meu OK para sair?"]] }`), `painel/src/App.tsx` (renderiza a tela; na carga, se `location.hash` (sem `#`) é o id de uma área, abre essa área)
- Test: `painel/tests/envios.test.tsx`

**Interfaces:**
- Consumes: Task 7. Siga `painel/src/telas/ContatosPropostas.tsx` para `useApi`, `useAcao`, toast e os componentes (`Bloco`, `Estados`, `Faixa`).

- [ ] **Step 1: Testes que falham** (no padrão de `painel/tests/telas.test.tsx`, com fetch falso):
  - O cartão de evento mostra conta, título, horário em Brasília (`qui 23/10 15:00–16:00`), e-mails e "vence".
  - O cartão de Teams mostra o destino e o texto completo.
  - Enviar faz `POST /api/v1/envios/{id}/enviar` com `{"hash": <hash da listagem>}` e recarrega.
  - Recusar chama `/recusar`.
  - Com `escrita: "desligado"` aparece a faixa "Envios desligados".
  - A lista "decididas" mostra estado e motivo.
  - `#envios` na URL abre a área.
- [ ] **Step 2: Rodar** `cd painel && npx vitest run tests/envios.test.tsx`. Esperado: falha.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** `cd painel && npx vitest run && npm run build`. Esperado: tudo passa e o build sai ok. Se houver teste que fixa a navegação, atualize-o.
- [ ] **Step 5: Commit** `feat(painel): área Envios com Enviar e Recusar`.

### Task 10: Documentação e passos do dono

**Files:**
- Modify: `docs/runbook.md` (seção `#envios` com os 5 passos do dono da spec, os comandos exatos, `sqlite3`/rota para gravar os parâmetros e como desligar: `envios.escrita` ≠ `"ligado"`), `docs/fontes/graph-ness.md` (as permissões novas e a delegada), `docs/fontes/google.md` (escopo `calendar.events`), `docs/BACKLOG.md` (AT1: "código pronto na branch, passos do dono no runbook `#envios`"), `docs/STATUS.md` (uma linha), `docs/ARQUITETURA.md` (uma linha sobre `gabi/envios`), `docs/PLANO-DEFINITIVO.md` (linha da Agenda: marcação com anuência = ADR-024)
- Test: suíte completa

- [ ] **Step 1: Escrever os docs** no tom dos atuais: pt-BR, curto, sem segredo.
- [ ] **Step 2: Rodar** `.venv/bin/python -m pytest -q 2>&1 | tail -5` e ler o resumo do pytest (não confiar no exit code de pipeline). Rodar também `cd painel && npx vitest run && npm run build`. Esperado: tudo passa.
- [ ] **Step 3: Commit** `docs: envios com anuência (runbook, fontes, backlog)`.
