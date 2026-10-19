# Graph da ness: base e agenda — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O brain lê contatos e agenda da `resper@ness.com.br` pelo Microsoft Graph, só leitura, com timers desligados.

**Architecture:** Um cliente novo `gabi/fontes/graph_ness.py` (client credentials com secret, token em cache) vive só no serviço de fontes e chega aos demais processos por uma ponte `graph_ness` (lista branca de métodos). A agenda reaproveita o motor de sincronização do Google: o cliente devolve o mesmo `ResultadoEventos` e `sincronizar` escolhe o cliente pelo `agenda_fonte.provedor` (`graph` já é aceito). Contatos reaproveitam `escuta.contatos.sincronizar` com um roteador de conta → fonte.

**Tech Stack:** Python 3.12, pytest, servidor HTTP falso injetado (`http(metodo, url, corpo, cab) -> (status, json)`), React/vitest só para um rótulo do painel.

**Spec:** `docs/superpowers/specs/2026-10-19-graph-ness-design.md` (partes 1 e 2; e-mail e Teams têm plano próprio depois).

## Global Constraints

- R2: nenhuma chamada de escrita, envio ou exclusão ao Graph nesta fase. Só `GET` e o `POST` do token. Um teste varre `graph_ness.py` por `"POST"`, `"PATCH"`, `"PUT"`, `"DELETE"` e só aceita o `POST` do token.
- R5: segredo (`M365_CLIENT_SECRET`), token e corpo de resposta nunca entram em exceção, log, `repr` ou aviso. Erro usa só `"<METODO> <caminho sem query> -> <status>"` (o formato `-> 401` é o que `CREDENCIAL` em `gabi/agenda/sincronizar.py` reconhece).
- Só a caixa `resper@ness.com.br`: contas permitidas = variável `M365_CONTAS` (padrão `resper@ness.com.br`), comparadas em minúsculas; qualquer outra conta levanta `ErroGraphNess("conta não permitida")` antes de qualquer rede.
- Texto de evento nunca em exceção, log ou aviso. Escopo de leitura apenas.
- Estilo do repositório: docstrings e mensagens em pt-BR, comentários só para o "porquê", nomes em pt-BR.
- Testes: `.venv/bin/pytest tests/fontes tests/agenda tests/escuta -q`; a suíte completa (`.venv/bin/pytest -q`) verde antes do último commit.
- Commits terminam com `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

- `sync_token` (o `deltaLink`) vem do banco: só é enviado com o Bearer se começar com `https://graph.microsoft.com/`; outro host levanta `ErroGraphNess("token de sincronização inválido")` sem rede (evita vazar o token do app).
- Paginação sem fim ou `@odata.nextLink` apontando para outro host: erro (`paginação sem fim`/`link inválido`), sem rede para o outro host.
- Evento `@removed` e `isCancelled` vão para `cancelados`; recusado pelo dono (`responseStatus.response == "declined"` do próprio) também.
- Dia inteiro (`isAllDay`) e evento com `dateTime` sem offset chegam a `tempo.de_google` corretos (data pura / `Z`).
- 410 `syncStateNotFound`/`resyncRequired` numa carga incremental → recarga completa da janela com `recarga_completa=True`.
- 429 (`Retry-After`) não é repetido em laço: vira `ErroGraphNess("... -> 429")` e a rodada seguinte tenta de novo.
- Recarga que volta vazia numa fonte com eventos já é tratada por `sincronizar_fonte` (não apaga); o teste de graph confirma o mesmo comportamento.
- Conta fora de `M365_CONTAS` em contatos, calendários e eventos.

## File Structure

- Create `gabi/fontes/graph_ness.py`: `ErroGraphNess`, `TokenApp`, `GraphNess` (contas, contatos, calendários, eventos), `graph_ness_do_ambiente`.
- Modify `gabi/fontes/ponte.py`: `PERMITIDOS`/`ERROS` e a classe `PonteGraph`.
- Modify `gabi/fontes/ambiente.py` e `gabi/fontes/servico.py`: registrar a fonte `graph_ness`.
- Modify `deploy/gabi-brain-fontes.service`: `EnvironmentFile=-/etc/gabi/graph-ness.env`.
- Create `deploy/normalizar-env-graph.sh`: tira espaços ao redor do `=` do arquivo de ambiente (passo do dono).
- Create `gabi/fontes/roteador.py`: `roteador_contatos(google, graph, contas_graph)`.
- Modify `gabi/escuta/contatos.py` (`main`), `gabi/rotas/escuta.py` (`sincronizar_contatos`): usar o roteador.
- Modify `gabi/agenda/sincronizar.py`, `gabi/agenda/fontes.py`, `gabi/agenda/__main__.py`, `gabi/rotas/agenda.py`: despacho por provedor.
- Modify `painel/src/telas/CadastrosAgenda.tsx` (+ `painel/tests/Agenda.test.tsx`): rótulo e botão "Descobrir calendários" para Microsoft.
- Create `tests/fontes/test_graph_ness.py`, `tests/fontes/test_roteador.py`; extend `tests/fontes/test_ponte.py`, `tests/agenda/test_sincronizar.py`, `tests/agenda/test_main.py`, `tests/escuta/test_contatos.py`.
- Create `docs/fontes/graph-ness.md`, `docs/adr/019-graph-ness.md`; update `docs/runbook.md`, `docs/STATUS.md`.

---

### Task 1: Token do app e núcleo HTTP

**Files:**
- Create: `gabi/fontes/graph_ness.py`
- Test: `tests/fontes/test_graph_ness.py`

**Interfaces:**
- Produces:
  - `class ErroGraphNess(Exception)`.
  - `class TokenApp: __init__(self, tenant: str, client_id: str, secret: str, http=http_real, agora=time.time)`; `__call__(self) -> str` (cache até 300 s antes de `expires_in`); `invalidar(self) -> None`; `__repr__` = `"TokenApp(<oculto>)"`.
  - `class GraphNess: __init__(self, token: Callable[[], str], contas: list[str], http=http_real)`; `contas(self) -> list[str]`; `_get(self, url: str, extra: dict | None = None) -> dict` (valida host, repete UMA vez após 401 com `token.invalidar()`, levanta `ErroGraphNess(f"GET {caminho} -> {status}")` em ≥400 e `ErroGraphNess("resposta inválida do Graph")` se o corpo não é dict, rede vira `ErroGraphNess("Graph indisponível: <NomeDaClasse>")`); `_conta(self, conta: str) -> str` (minúscula, valida contra `contas`); `__repr__` = `"GraphNess(<oculto>)"`.
  - `graph_ness_do_ambiente(env) -> GraphNess | None`: `None` sem `M365_TENANT_ID`, `M365_CLIENT_ID` ou `M365_CLIENT_SECRET`; `contas` vem de `M365_CONTAS` (separado por vírgula) com padrão `["resper@ness.com.br"]`.
  - Constantes `BASE = "https://graph.microsoft.com/v1.0"`, `LOGIN = "https://login.microsoftonline.com"`, `MAX_PAGINAS = 200`.

- [ ] **Step 1: Write the failing tests** em `tests/fontes/test_graph_ness.py`, com um `http` falso que consome uma fila de `(status, corpo)` e guarda `(metodo, url, corpo, cab)`:
  - `test_token_troca_credenciais_e_cacheia`: duas chamadas a `TokenApp()` fazem 1 `POST` a `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` com `grant_type=client_credentials` e `scope=https://graph.microsoft.com/.default` no corpo; passados `expires_in - 301` s ainda usa cache, passados `expires_in - 299` s troca de novo (relógio injetado).
  - `test_token_erro_nao_vaza_segredo`: resposta 401 com corpo contendo o secret → `ErroGraphNess` cuja `str` não contém o secret nem o corpo.
  - `test_repr_nao_mostra_segredo`: `repr(TokenApp(..., "SEGREDO-1"))` e `repr(GraphNess(...))` não contêm `SEGREDO-1`.
  - `test_get_repete_uma_vez_apos_401`: 401 então 200 → devolve o dict e chamou `token.invalidar` 1 vez; 401, 401 → `ErroGraphNess` com `-> 401`.
  - `test_get_recusa_outro_host`: `_get("https://evil.example/x")` levanta `ErroGraphNess("link inválido")` sem chamar o `http`.
  - `test_get_erro_formato`: `500` → mensagem exata `"GET /v1.0/users/x/y -> 500"` (sem query); corpo lista → `"resposta inválida do Graph"`; `ConnectionError` do http → `"Graph indisponível: ConnectionError"`.
  - `test_conta_fora_da_lista_e_recusada`: `_conta("outro@ness.com.br")` levanta `ErroGraphNess("conta não permitida")`; `_conta("RESPER@ness.com.br")` devolve `"resper@ness.com.br"`.
  - `test_do_ambiente`: sem as 3 variáveis → `None`; com elas → `GraphNess` com `contas() == ["resper@ness.com.br"]`; com `M365_CONTAS="a@x.com, B@x.com"` → `["a@x.com","b@x.com"]`.
  - `test_so_leitura_no_codigo`: o texto de `graph_ness.py` não contém `"PATCH"`, `"PUT"`, `"DELETE"`, e contém `"POST"` uma única vez.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/fontes/test_graph_ness.py -q`. Expected: FAIL (`ModuleNotFoundError: gabi.fontes.graph_ness`).

- [ ] **Step 3: Implement** `gabi/fontes/graph_ness.py` com as assinaturas acima. O token faz `POST` form-urlencoded (o `http_real` envia JSON; para o token use `urllib` próprio injetável via o mesmo parâmetro `http` com `corpo` como `str` já codificado e cabeçalho `Content-Type: application/x-www-form-urlencoded` — ajuste `gabi/fontes/_http.py::http_real` para enviar `str`/`bytes` como estão, mantendo o comportamento atual para dict). `_get` valida `url.startswith(BASE + "/")` ou o prefixo `https://graph.microsoft.com/` (para `@odata.nextLink`/`deltaLink`), monta a mensagem de erro com `urllib.parse.urlsplit(url).path`.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/fontes/test_graph_ness.py tests/fontes -q`. Expected: PASS (inclui o que já existia de `_http`).

- [ ] **Step 5: Commit** `git add gabi/fontes/graph_ness.py gabi/fontes/_http.py tests/fontes/test_graph_ness.py && git commit -m "feat(graph-ness): token do app e núcleo HTTP só leitura"`.

---

### Task 2: Contatos do Graph

**Files:**
- Modify: `gabi/fontes/graph_ness.py`
- Test: `tests/fontes/test_graph_ness.py`

**Interfaces:**
- Consumes (Task 1): `GraphNess._get`, `_conta`, `ErroGraphNess`, `MAX_PAGINAS`.
- Produces: `GraphNess.contatos(self, conta: str) -> list[dict]` com o mesmo formato de `google_contatos.listar_contatos`: `[{"nome": str|None, "telefone": str|None[, "emails": list[str]]}]`, um item por telefone, contato só com e-mail vira um item com `telefone: None`.

- [ ] **Step 1: Write the failing tests:**
  - `test_contatos_um_item_por_telefone_com_emails`: contato `{displayName:"Ana", mobilePhone:"+55 11 99999-0000", homePhones:["1133334444"], businessPhones:[], emailAddresses:[{address:"Ana@X.com"},{address:"ana@x.com"}]}` → dois itens (`mobilePhone` primeiro, depois `homePhones`), ambos com `emails == ["ana@x.com"]` (minúsculo, sem repetir, máx. 10, só endereço que casa com a regex `_EMAIL` de `gabi.fontes.google_contatos`).
  - `test_contatos_so_email`: sem telefones → `[{"nome":"Ana","telefone":None,"emails":["ana@x.com"]}]`; sem nada → nenhum item.
  - `test_contatos_pagina_e_pede_so_campos_necessarios`: segue `@odata.nextLink` (2 páginas); a 1ª URL é `…/users/resper%40ness.com.br/contacts` com `$select=displayName,mobilePhone,homePhones,businessPhones,emailAddresses` e `$top=100`.
  - `test_contatos_paginacao_sem_fim`: `nextLink` repetido → `ErroGraphNess("paginação sem fim")`; mais de `MAX_PAGINAS` páginas também.
  - `test_contatos_conta_nao_permitida`: sem rede.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/fontes/test_graph_ness.py -k contatos -q`. Expected: FAIL (`AttributeError: contatos`).

- [ ] **Step 3: Implement** `GraphNess.contatos` reutilizando `_EMAIL`/`MAX_EMAILS` de `gabi.fontes.google_contatos` (importe os nomes, não copie a regex). Ordem dos telefones: `mobilePhone`, `homePhones`, `businessPhones`; telefone vazio é ignorado. Nunca guardar nem devolver outros campos.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/fontes/test_graph_ness.py -q`. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -am "feat(graph-ness): contatos (nome, telefone, e-mail)"` (após `git add` dos dois arquivos).

---

### Task 3: Ponte, serviço e roteador de contatos

**Files:**
- Modify: `gabi/fontes/ponte.py` (`PERMITIDOS`, `ERROS`, nova `PonteGraph`), `gabi/fontes/ambiente.py`, `gabi/fontes/servico.py`, `deploy/gabi-brain-fontes.service`, `gabi/escuta/contatos.py` (`main`), `gabi/rotas/escuta.py` (`sincronizar_contatos`)
- Create: `gabi/fontes/roteador.py`, `deploy/normalizar-env-graph.sh`
- Test: `tests/fontes/test_ponte.py`, `tests/fontes/test_roteador.py`, `tests/escuta/test_contatos.py`

**Interfaces:**
- Consumes (Task 1–2): `GraphNess.contas() -> list[str]`, `GraphNess.contatos(conta)`; `graph_ness_do_ambiente(env)`.
- Produces:
  - `PERMITIDOS["graph_ness"] = frozenset({"contas", "contatos", "listar_calendarios", "listar_eventos"})` e `ERROS["graph_ness"] = ErroGraphNess`.
  - `class PonteGraph: __init__(self, caminho)`; `configurada() -> bool`; `contas() -> list[str]`; `contatos(conta) -> list[dict]`; `listar_calendarios(conta) -> list[dict]`; `listar_eventos(conta, calendario_id, sync_token, janela) -> ResultadoEventos` (os dois últimos usados na Task 5; validam a forma como `PonteAgenda`, levantando `ErroGraphNess("resposta inválida do serviço de fontes")`).
  - `fontes_do_ambiente()` (modo socket) ganha a chave `"graph_ness"`; `servico.main` acrescenta `fontes["graph_ness"] = graph_ness_do_ambiente(os.environ)`.
  - `roteador_contatos(google: Callable[[str], list[dict]] | None, graph: Callable[[str], list[dict]] | None, contas_graph: list[str]) -> Callable[[str], list[dict]]`: conta (minúscula) em `contas_graph` → `graph`, senão `google`; fonte ausente (`None`) levanta `ErroGoogleOAuth("conta não autorizada: <conta>")` para cair no aviso esperado.

- [ ] **Step 1: Write the failing tests:**
  - `test_ponte.py::test_graph_ness_metodos_permitidos`: o servidor de teste existente atende `graph_ness.contatos` com um objeto falso e recusa `graph_ness.enviar` (erro de método não permitido), no mesmo estilo dos testes atuais de `google_agenda`.
  - `test_ponte.py::test_ponte_graph_valida_forma`: resposta de `listar_eventos` sem `cancelados` → `ErroGraphNess("resposta inválida do serviço de fontes")`.
  - `test_roteador.py::test_roteia_por_conta`: `resper@ness.com.br` vai ao `graph`, `resper@gmail.com` ao `google`; comparação sem diferenciar caixa.
  - `test_roteador.py::test_fonte_ausente_vira_nao_autorizada`: `graph=None` e conta da ness → `ErroGoogleOAuth` com texto começando em `conta não autorizada`.
  - `test_contatos.py::test_main_usa_roteador`: `main(banco, listar=...)` continua aceitando `listar` injetado (sem regressão); e um teste de `sincronizar` com o roteador gravando a conta ness a partir do falso do Graph.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/fontes/test_ponte.py tests/fontes/test_roteador.py tests/escuta/test_contatos.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** ponte, registro e roteador conforme Interfaces. Em `escuta/contatos.py::main` e `rotas/escuta.py::sincronizar_contatos`, quando o `listar` não vem injetado, monte `roteador_contatos(ponte_google.listar, ponte_graph.listar... )` apenas se `PonteGraph(sock).configurada()`; `contas_graph = PonteGraph.contas()`. Sem a fonte do Graph, o comportamento atual (só Google) não muda. `deploy/gabi-brain-fontes.service`: acrescentar `EnvironmentFile=-/etc/gabi/graph-ness.env` depois do `google.env`, com comentário de uma linha. `deploy/normalizar-env-graph.sh`: `bash` com `set -euo pipefail`, root, faz backup `.bak-AAAAMMDD` e reescreve `KEY =valor`/`KEY = valor` como `KEY=valor` com `sed -E 's/^([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*/\1=/'`, mantém dono e modo (`root:gabibrain 0640`), imprime só os nomes das chaves, nunca os valores.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/fontes tests/escuta -q`. Expected: PASS. Rodar também `bash -n deploy/normalizar-env-graph.sh` (sem saída = ok).

- [ ] **Step 5: Commit** `git add -A gabi deploy tests && git commit -m "feat(graph-ness): ponte, serviço de fontes e roteador de contatos"`.

---

### Task 4: Agenda do Graph (cliente)

**Files:**
- Modify: `gabi/fontes/graph_ness.py`
- Test: `tests/fontes/test_graph_ness.py`

**Interfaces:**
- Consumes: `GraphNess._get(url, extra)`, `_conta`, `MAX_PAGINAS`; `ResultadoEventos` de `gabi.fontes.google_agenda` (`eventos: list[dict]`, `cancelados: list[str]`, `novo_sync_token: str|None`, `recarga_completa: bool`).
- Produces:
  - `GraphNess.listar_calendarios(self, conta: str) -> list[dict]`: `[{"id", "nome", "principal"}]` de `GET /users/{conta}/calendars`; `principal` = `isDefaultCalendar is True`.
  - `GraphNess.listar_eventos(self, conta: str, calendario_id: str, sync_token: str | None, janela: dict) -> dict` (JSON puro: `asdict(ResultadoEventos)`).
  - Mapeamento do evento (chaves iguais às de `google_agenda._evento`): `externo_id`←`id`; `inicio`/`fim`←`{"dateTime": "<ISO>Z"}` (UTC; `Prefer: outlook.timezone="UTC"`) ou `{"date": "AAAA-MM-DD"}` quando `isAllDay`; `titulo`←`subject` (só `str`); `link_reuniao`←`onlineMeeting.joinUrl` só se `https://`; `participantes_qtd`←`len(attendees)`; `status`←`"confirmed"`; `etag`←`@odata.etag`; `atualizado_origem`←`lastModifiedDateTime`; `privado`←`sensitivity in ("private","confidential")`; `ical_uid`←`iCalUId`; `livre`←`showAs == "free"`.

- [ ] **Step 1: Write the failing tests** (http falso por URL):
  - `test_calendarios`: dois calendários, o de `isDefaultCalendar` com `principal True`.
  - `test_eventos_carga_completa_pede_delta_com_janela`: 1ª chamada é `GET /v1.0/users/resper%40ness.com.br/calendarView/delta?startDateTime=<de>&endDateTime=<ate>` para `calendario_id="primary"` e `/calendars/<id>/calendarView/delta` para outro id; cabeçalhos `Prefer: outlook.timezone="UTC", odata.maxpagesize=200`; segue `@odata.nextLink`; devolve `novo_sync_token` = `@odata.deltaLink` da última página e `recarga_completa False`.
  - `test_eventos_incremental_usa_o_delta_link`: com `sync_token="https://graph.microsoft.com/v1.0/...?$deltatoken=abc"` a 1ª URL é exatamente esse link (sem `startDateTime`).
  - `test_sync_token_de_outro_host_e_recusado`: `sync_token="https://evil.example/d"` → `ErroGraphNess("token de sincronização inválido")`, `http` não chamado.
  - `test_mapeamento`: evento comum (UTC `…T13:00:00.0000000` vira `…T13:00:00Z` e `tempo.de_google` o aceita), dia inteiro (`isAllDay`, `start 2026-10-12T00:00:00.0000000` → `{"date":"2026-10-12"}` e fim `2026-10-13`), `joinUrl` `http://` descartado, `sensitivity private` → `privado True`, `showAs free` → `livre True`, 3 participantes → `participantes_qtd 3`, `subject` ausente → `titulo None`.
  - `test_removido_cancelado_e_recusado_vao_para_cancelados`: `{"id":"r","@removed":{"reason":"deleted"}}`, `isCancelled True`, e evento com `responseStatus.response=="declined"` do dono (`responseStatus` do próprio evento, campo de topo) → `cancelados == ["r","c","d"]`.
  - `test_410_incremental_vira_recarga`: delta incremental responde `410` com `error.code` `syncStateNotFound` → refaz a carga completa da janela e devolve `recarga_completa True`; `410` numa carga completa → `ErroGraphNess` `-> 410`.
  - `test_429_nao_e_repetido`: `429` → `ErroGraphNess` com `-> 429` e uma só chamada.
  - `test_pagina_sem_fim_e_link_de_outro_host`: `nextLink` repetido → `paginação sem fim`; `nextLink` de outro host → `link inválido`.
  - `test_calendario_invalido`: id com `/` ou espaço → `ErroGraphNess("calendário inválido")`; janela sem `de`/`ate` → `ErroGraphNess("janela inválida")`.
  - `test_evento_sem_id_e_pulado`: item sem `id` string não entra nem em `eventos` nem em `cancelados`.

- [ ] **Step 2: Run** `.venv/bin/pytest tests/fontes/test_graph_ness.py -k "calendarios or eventos or removido or 410 or 429 or pagina or invalido" -q`. Expected: FAIL.

- [ ] **Step 3: Implement** os dois métodos. `_get` precisa distinguir `410` numa carga incremental: faça `_get_ou_none(url, extra) -> dict | None` (devolve `None` só para `410`) usado apenas pelo caminho incremental. `calendario_id` aceito: `"primary"` ou o padrão `^[A-Za-z0-9=_.-]{1,300}$` (ids do Graph são base64 com `=`); codifique com `urllib.parse.quote(..., safe="")`. `janela["de"]`/`["ate"]` são ISO com offset (UTC) e vão na query tal como vêm.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/fontes -q`. Expected: PASS.

- [ ] **Step 5: Commit** `git add gabi/fontes/graph_ness.py tests/fontes/test_graph_ness.py && git commit -m "feat(graph-ness): calendários e eventos (delta, só leitura)"`.

---

### Task 5: Agenda — despacho por provedor, descoberta, painel

**Files:**
- Modify: `gabi/agenda/sincronizar.py` (`sincronizar`, `sincronizar_fonte`), `gabi/agenda/fontes.py` (`descobrir_calendarios`), `gabi/agenda/__main__.py`, `gabi/rotas/agenda.py` (`descobrir`), `painel/src/telas/CadastrosAgenda.tsx`
- Test: `tests/agenda/test_sincronizar.py`, `tests/agenda/test_main.py`, `tests/agenda/test_fontes.py` (se existir; senão no `test_sincronizar.py`), `tests/rotas/` (teste de descobrir existente), `painel/tests/Agenda.test.tsx`

**Interfaces:**
- Consumes: `PonteGraph.listar_eventos(conta, calendario_id, sync_token, janela) -> ResultadoEventos`, `PonteGraph.listar_calendarios(conta) -> list[dict]`, `ErroGraphNess`.
- Produces:
  - `sincronizar(con, listar, agora, *, listar_graph=None) -> dict`: fonte `google` usa `listar`; fonte `graph` usa `listar_graph`; `graph` sem `listar_graph` → `{"erro": "provedor sem cliente ainda"}`. `auth` continua exigindo `oauth` (rótulo reaproveitado para o `graph`).
  - A mensagem do erro entra no resultado/`ultimo_erro` também para `ErroGraphNess` (hoje só `ErroGoogleOAuth`); os padrões `CREDENCIAL`/`SO_STATUS_403` seguem valendo e disparam `agenda_reconectar`.
  - `descobrir_calendarios(con, fonte_id, listar_calendarios)` aceita `provedor in ("google","graph")`; a rota usa `PonteGraph.listar_calendarios` quando `f["provedor"] == "graph"` (fonte `graph_ness`, 503 `fonte_indisponivel` se ausente).
  - `python -m gabi.agenda`: monta `listar_graph` quando `PonteGraph(sock).configurada()`; a agenda do Google deixa de ser obrigatória se só há fonte `graph` (retorna 2 só se NENHUMA das duas pontes está configurada).

- [ ] **Step 1: Write the failing tests:**
  - `test_sincronizar.py::test_fonte_graph_usa_o_cliente_graph`: fonte `provedor='graph'`, `sincronizar(con, listar_google_que_falha, AGORA, listar_graph=falso)` grava os eventos e nunca chama o do Google; e uma fonte `google` ao lado continua usando o do Google.
  - `test_sincronizar.py::test_graph_sem_cliente_nao_derruba_as_outras`: `listar_graph=None` → `{"erro": "provedor sem cliente ainda"}` só para a fonte graph.
  - `test_sincronizar.py::test_erro_do_graph_aparece_tipado_e_reconecta_no_401`: `ErroGraphNess("GET /v1.0/users/x/calendarView/delta -> 401")` → `ultimo_erro` com a mensagem e aviso `agenda_reconectar`; um `RuntimeError("segredo")` continua mostrando só o nome da classe.
  - `test_fontes.py::test_descobrir_calendarios_graph`: cria uma conta `graph`, descobre `[{"id":"AAA=","nome":"Calendar","principal":True},{"id":"BBB=","nome":"Feriados","principal":False}]` → duas fontes `a_decidir` (`primary` e `BBB=`), `auth` herdado.
  - `test_main.py::test_main_so_graph`: com `listar_graph` injetado e uma fonte `graph` liberada, `main(banco, listar=None, listar_graph=falso)` imprime `agenda: fontes=1 ok=1` e sai 0 (adapte `main` para aceitar `listar_graph`).
  - Rota: teste do `POST /api/v1/agenda/fontes/{id}/calendarios/descobrir` para fonte `graph` com `fontes["graph_ness"]` falsa devolve os calendários; sem a fonte, 503 `fonte_indisponivel`.
  - Painel (`Agenda.test.tsx`): o `<option>` é "Microsoft" (sem "ainda não lê") e fonte `graph` com `calendario_id === "primary"` mostra o botão "Descobrir calendários".

- [ ] **Step 2: Run** `.venv/bin/pytest tests/agenda tests/rotas -q -k "graph or descobrir"` e `cd painel && npx vitest run tests/Agenda.test.tsx`. Expected: FAIL.

- [ ] **Step 3: Implement** o despacho e as trocas acima. Em `sincronizar_fonte` mantenha a assinatura `(con, fonte_id, listar, agora)` (o `listar` recebido já é o cliente certo; quem escolhe é `sincronizar`). No painel troque o rótulo para `Microsoft` e o `f.provedor === "google" &&` do botão por `(f.provedor === "google" || f.provedor === "graph") &&`.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/agenda tests/rotas tests/fontes -q` e `cd painel && npx vitest run`. Expected: PASS.

- [ ] **Step 5: Commit** `git add -A gabi painel tests && git commit -m "feat(agenda): fonte Microsoft (Graph) lida pelo mesmo motor"`.

---

### Task 6: Documentação, instalação e conferência

**Files:**
- Create: `docs/fontes/graph-ness.md`, `docs/adr/019-graph-ness.md`
- Modify: `docs/runbook.md` (seção nova `{#graph-ness}`), `docs/STATUS.md`, `docs/BACKLOG.md` (linha 109 e a de "Graph só quando a ness migrar"), `deploy/instalar.sh` (nada novo a copiar além da unit; confirmar)

- [ ] **Step 1: Escrever `docs/fontes/graph-ness.md`:** app `ness-automacao` (tenant e client id NÃO vão no texto; só "em `/etc/gabi/graph-ness.env`"), permissões de aplicativo necessárias e a lista a remover (`Application.ReadWrite.All`, `Sites.FullControl.All`, `Calendars.ReadWrite.All`, `Contacts.ReadWrite`), política de acesso do Exchange para `resper@ness.com.br`, formato do arquivo (`M365_TENANT_ID`, `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_CONTAS` opcional, sem espaços ao redor do `=`), o que cada método lê e nunca faz.
- [ ] **Step 2: Escrever `docs/adr/019-graph-ness.md`** (decisão: secret em vez de certificado para a ness, mesmo motor da agenda, ponte própria, só leitura) e a seção `{#graph-ness}` do runbook com os passos do dono em ordem: (1) `sudo ~/normalizar-env-graph.sh` (copiar `deploy/normalizar-env-graph.sh` para `~`), (2) `deploy/instalar.sh`, (3) `sudo systemctl restart gabi-brain-fontes` e conferir `fontes configuradas` com `graph_ness: True` no `journalctl`, (4) Painel › Cadastros › Agenda: cadastrar `resper@ness.com.br` como Microsoft, Descobrir calendários, Liberar, (5) Escuta › Contatos › Sincronizar, (6) ligar o timer da agenda só depois de conferir uma rodada à mão (`sudo -u gabibrain env GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock /opt/gabi-brain/venv/bin/python -m gabi.agenda`).
- [ ] **Step 3: Atualizar `docs/STATUS.md`** (bloco novo no topo: "Graph da ness (19/10/2026): código pronto, nada ligado") e `docs/BACKLOG.md`.
- [ ] **Step 4: Run** `.venv/bin/pytest -q 2>&1 | tail -5` e `cd painel && npx vitest run 2>&1 | tail -5`. Expected: tudo verde (ler o resumo do pytest, não só o código de saída).
- [ ] **Step 5: Commit** `git add docs deploy && git commit -m "docs: Graph da ness (fonte, ADR-019, runbook, status)"`.
