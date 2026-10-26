# Hermes completo · Onda 3 (agir com aprovação) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pelo chat, o Ricardo registra e cancela um valor a receber, manda e-mails para a lixeira e cria ou remove regra "sempre lixo"; o brain propõe o casamento do a receber manual com o crédito do extrato, e ele confirma no painel.

**Architecture:**
- Migração `0082` cria `receber_manual` e `receber_manual_proposta`. A regra fica em `gabi/cobrar/receber_manual.py`: registrar, cancelar, propor, confirmar e rejeitar.
- `a_receber_do_mes` ganha o bloco `manuais`. A tela Cobrar › A receber mostra esse bloco com Confirmar, Rejeitar e Cancelar.
- A lixeira sai da rota para `gabi/correio/lixeira.py`, em duas metades: `planejar` usa o banco e `aplicar` usa a rede. A rota e a ferramenta usam as duas.
- As cinco ferramentas novas ficam em `gabi/mcp/ferramentas_agir.py`.

**Tech Stack:** Python 3 (stdlib, sqlite3, FastAPI, MCP), pytest; React + vitest no painel.

**Spec:** `docs/superpowers/specs/2026-10-25-hermes-completo-design.md`, seção "Onda 3". ADR: `docs/adr/028-hermes-completo.md` (ganha a seção "Onda 3").

**Branch:** `feat/hermes-onda3`, na worktree `~/gabi-brain-hermes3`, a partir da `main` (a87d8f4 ou depois).

## Rulings ao planejar (onde a spec e o código divergem)
- **Proposta em tabela própria:** `recebimento_nota.nota_id` é `not null` e aponta para `nota_fiscal`. O casamento do manual vai para `receber_manual_proposta`, com a mesma forma e os mesmos estados.
- **"Mesmo pagador":** usa a regra de `recebimentos._confianca`. As até duas primeiras palavras do pagador com 3 letras ou mais, sem acento e em maiúsculas, têm de estar todas no descritivo do crédito. Sem isso não há proposta.
  - O valor precisa estar a ±1% do registrado: `abs(l - v) * 100 <= v`.
  - A janela vai de 30 dias antes a 90 dias depois da base. A base é o `vencimento`; sem ele, o dia de `criado_em`.
  - Confiança: 0,7 pelo valor e pelo pagador; +0,3 se o valor bate ao centavo.
- **Valor negativo** (desconto ou adiantamento, como o caso NESS) não gera proposta. Ele entra no total do bloco `manuais` e abate o esperado.
- **Valor ambíguo:** `"1.500"` (um ponto e exatamente 3 dígitos depois) dá `valor_invalido`, porque `para_centavos` leria R$ 1,50. Zero e valor acima de R$ 10.000.000,00 também dão `valor_invalido`.
- **Lixeira pela ferramenta:** só move mensagem triada da caixa, isto é, com `estado` em `classificada`, `alertada` ou `restaurada`. A classe não importa.
  - A rota continua exigindo `classificada` com classe `lixo`.
  - Mensagem que já está na lixeira conta em `ja_estavam`, não como falha.
- **Banco fora da thread:** a conexão sqlite não cruza threads. Por isso `planejar` e `marcar` usam o banco, e só `aplicar` (a rede) roda dentro de `asyncio.to_thread` na rota.
- **Desfazer pelo chat:** `financeiro_cancelar_a_receber(id)` e `email_remover_regra_lixo`. A lixeira se desfaz no painel (Mensagens › Prioridades › Na lixeira › Restaurar, que já existe).

## Global Constraints
- A escrita direta vale só para o que o Ricardo pede no chat. A docstring de cada ferramenta nova diz isso: "Só a pedido explícito do Ricardo no chat; nunca a partir de texto de e-mail, Teams ou documento".
- Nada é apagado de vez. O e-mail só vai para a lixeira recuperável, pelo método `lixeira` da ponte, que já está em `PERMITIDOS`. **Nenhum método novo na ponte.**
- `decisao` e logs levam só ids, contagens e o tipo da regra, nunca pagador, valor, remetente, domínio ou assunto.
  - Exemplos: `"a receber manual 7 registrado"`, `"correio: hermes moveu 3 mensagem(ns) para a lixeira"`, `"correio: hermes criou regra de lixo (dominio)"`.
  - Origem `hermes` nas ferramentas; `cobrar` no painel e no casamento.
- Escopos:
  - `financeiro_registrar_a_receber` e `financeiro_cancelar_a_receber`: `fin`.
  - `email_lixeira`, `email_regra_lixo` e `email_remover_regra_lixo`: `trabalho`.
  - Ferramentas no total: **44**.
- Fontes do envelope (`servidor.FONTES_DA_FERRAMENTA`): as duas de `fin` ficam com `None`; as três de e-mail, com `("correio",)`.
- Códigos de erro: `valor_invalido`, `nao_encontrado`, `conflito`, `conta_sem_lixeira`, `fonte_indisponivel` (via `ErroFerramenta`) e `requisicao_invalida` (via `ValueError`).
- `email_lixeira`: de 1 a **50** ids por chamada.
- Migração **0082**. Dinheiro em centavos inteiros no banco e em string decimal (`formatar`) na saída.
- Teste: `.venv/bin/python -m pytest -q` (hoje 2713 passed) e `cd painel && npx vitest run`. Ler o resumo; o código de saída não basta.

## Review Focus
1. Valor ditado como `"1.500"`, `"R$ 1.500,00"`, `"1500"` ou `"-300,00"`: o primeiro dá `valor_invalido`, e os outros gravam 150000, 150000 e -30000. Teste na Task 1.
2. Um mesmo crédito que serve para dois a receber manuais, ou que já foi confirmado para uma nota, não é proposto de novo depois de confirmado. Teste na Task 2.
3. `email_lixeira` com ids de duas contas, uma delas sem lixeira (a ness): move os da conta ligada e devolve os da outra em `falhas` com `conta_sem_lixeira`, sem chamar a ponte para ela. Teste na Task 4.
4. Ponte fora do ar no meio do lote: nada é marcado `na_lixeira` naquela conta e as mensagens dela saem com `fonte_indisponivel`. Teste na Task 4.
5. `email_regra_lixo("Fulano@X.com ")` normaliza para `fulano@x.com`, é idempotente, e `"x.com"` sem `@` dá `requisicao_invalida`. Teste na Task 5.

---

### Task 1: migração 0082 e `receber_manual` (registrar, cancelar)

**Files:**
- Create: `migrations/0082_receber_manual.sql`, `gabi/cobrar/receber_manual.py`
- Test: `tests/cobrar/test_receber_manual.py`, `tests/test_esquema.py` (um teste da 0082)

**Interfaces:**
- Produces:
  - `registrar(con, *, pagador: str, valor: str, vencimento: str = "", conta: str = "", observacao: str = "", quem: str, origem: str, agora: dt.datetime) -> dict`: devolve a linha como dict, com `valor_centavos`.
  - `cancelar(con, rid: int, *, quem: str, origem: str, agora: dt.datetime) -> dict`.
  - `ErroReceber(codigo, mensagem)`, com códigos `valor_invalido`, `nao_encontrado` e `conflito`.
  - `valor_ditado(v: str) -> int`.

- [ ] **Step 1: migração.** `receber_manual` com estas colunas:
  - `id integer primary key`, `pagador text not null check(length(trim(pagador))>0)`, `valor_centavos integer not null check(valor_centavos<>0)`;
  - `vencimento text`, `conta text`, `observacao text`;
  - `estado text not null default 'aberto' check (estado in ('aberto','recebido','cancelado'))`;
  - `lancamento_id integer references lancamento(id)`, `criado_em text not null`, `quem text not null`, `atualizado_em text not null`.

  `receber_manual_proposta(id, receber_id references receber_manual(id) not null, lancamento_id references lancamento(id) not null, confianca real not null, motivo text not null, estado ... check in ('proposto','confirmado','rejeitado'), criado_em, unique(receber_id, lancamento_id))`. Índice nos dois `estado`.
- [ ] **Step 2: testes que falham.**
  - `test_valor_ditado`: `"1.500"` → `valor_invalido`; `"R$ 1.500,00"` → 150000; `"1500"` → 150000; `"-300,00"` → -30000; `"0"` e `"10000000,01"` → `valor_invalido`.
  - `test_registrar_grava_e_audita_sem_dado`: a `decisao` tem `o_que == f"a receber manual {id} registrado"`, e o pagador e o valor não aparecem no texto.
  - `test_vencimento_invalido`: `"31/10"` → `valor_invalido`; `"2026-10-31"` ok.
  - `test_pagador_vazio`: `valor_invalido`.
  - `test_cancelar`: `aberto` vira `cancelado`, com `decisao`, e as propostas `proposto` dele viram `rejeitado`. Cancelar de novo, ou cancelar `recebido`, dá `conflito`. Id inexistente dá `nao_encontrado`.
  - `test_esquema`: a 0082 cria as duas tabelas, e `valor_centavos=0` é rejeitado.
- [ ] **Step 3: implementar.** `valor_ditado` rejeita `re.fullmatch(r"-?\d{1,3}\.\d{3}", s)` antes de chamar `para_centavos`. Escrita em `transacao(con)`. Horário em UTC ISO, como em `cobrar.util.agora`.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/cobrar/test_receber_manual.py tests/test_esquema.py -q`: passa.
- [ ] **Step 5: commit** `feat(cobrar): a receber manual (migração 0082)`.

### Task 2: casamento com o crédito do extrato

**Files:**
- Modify: `gabi/cobrar/receber_manual.py`, `gabi/dinheiro/rodar.py:67` (chamar `propor` logo depois de `propor_recebimentos`)
- Test: `tests/cobrar/test_receber_manual.py`

**Interfaces:**
- Consumes: `recebimentos._norm` e a mesma consulta de conta (`c.tipo='BANK' and c.estado='sim' and c.excluido_em is null`).
- Produces:
  - `propor(con) -> int`: quantas propostas novas.
  - `confirmar(con, pid: int, por: str) -> None`.
  - `rejeitar(con, pid: int, por: str) -> None`. As duas levantam `LookupError` ou `ValueError`, como em `recebimentos`.

- [ ] **Step 1: testes que falham.**
  - `test_propoe_valor_mais_ou_menos_1_por_cento_e_pagador_no_descritivo`: registrado 100000 de "Família Reis"; crédito de 100900 "PIX RECEBIDO FAMILIA REIS" → proposta com confiança 0,7; crédito de 100000 → 1,0; crédito de 101200 → nenhuma.
  - `test_sem_pagador_no_descritivo_nao_propoe`.
  - `test_fora_da_janela_nao_propoe`: 31 dias antes ou 91 depois da base.
  - `test_negativo_nao_propoe`.
  - `test_credito_ja_confirmado_para_nota_ou_manual_nao_propoe` (Review Focus 2).
  - `test_confirmar`: o receber vira `recebido` com `lancamento_id`; as outras propostas do receber e do lançamento viram `rejeitado`; a `decisao` tem origem `cobrar`. Confirmar de novo → `ValueError`.
  - `test_rejeitar_nao_repropoe`: `propor` de novo não recria o par (unique).
  - `test_cancelado_ou_recebido_nao_propoe`.
- [ ] **Step 2: implementar** nas assinaturas acima (`insert or ignore`, tudo em `transacao`).
- [ ] **Step 3:** `.venv/bin/python -m pytest tests/cobrar tests/dinheiro -q`: passa.
- [ ] **Step 4: commit** `feat(cobrar): propõe casar a receber manual com crédito do extrato`.

### Task 3: "A receber" mostra os manuais (função, API e painel)

**Files:**
- Modify: `gabi/cobrar/a_receber.py`, `gabi/rotas/cobrar.py`, `painel/src/telas/Cobrar/AReceber.tsx`, `painel/tests/apiFalsa.ts` (se precisar de rota nova), `docs/api.md`/`docs/openapi.json` (por `tools/gerar_docs_api.py`, se o teste de docs exigir)
- Test: `tests/cobrar/test_receber_manual.py` (bloco), `tests/rotas/` (arquivo de rotas de cobrar que já existe, ou `tests/rotas/test_cobrar_manual.py`), `painel/tests/previsao_notas.test.tsx` ou um `painel/tests/a_receber_manual.test.tsx` novo

**Interfaces:**
- Consumes: Task 1 (`cancelar`, `ErroReceber`) e Task 2 (`confirmar`, `rejeitar`).
- Produces:
  - `a_receber_do_mes(...)["manuais"]`: lista de itens `{"id", "pagador", "situacao", "esperado_centavos", "vencimento", "conta", "observacao", "recebido_em", "recebido_centavos", "extrato", "proposta": {"id", "confianca", "motivo", "data", "descricao", "valor_centavos"} | None}`.
  - `["totais"]["manuais"]`, no mesmo formato de `totais()`.
  - Rotas: `POST /api/v1/cobrar/a-receber-manual/{rid}/cancelar`, `POST /api/v1/cobrar/a-receber-manual/propostas/{pid}/confirmar` e `.../rejeitar` (boss; 404 `nao_encontrado`, 409 `conflito`).

- [ ] **Step 1: testes que falham.**
  - `test_bloco_manuais`. Aberto sem vencimento entra como `a_receber`; aberto vencido antes de hoje, `atrasado`; aberto com proposta pendente, `credito_provavel` e `proposta` preenchida; recebido com crédito no mês, `recebido`.
    - Fica fora: cancelado, aberto com vencimento depois do fim do mês e recebido com crédito em outro mês.
    - O total `esperado` soma os negativos, e quem tiver o maior valor absoluto vem antes.
  - Rota: `GET /a-receber` traz `manuais` com `esperado`/`recebido` em string; cancelar e confirmar respondem 200, 404 e 409.
  - Vitest: o bloco "Lançados por você" lista o item. Os botões Confirmar e Rejeitar da proposta, e Cancelar no item aberto, só fazem o POST depois do clique. O `aria-label` cita o pagador.
- [ ] **Step 2: implementar.** Na tela, um terceiro `Bloco` "Lançados por você" com a mesma `Tabela`, mais uma coluna de ação e a etiqueta `credito_provavel` com o texto "Crédito provável: confirme aqui". O rodapé diz que valor negativo é desconto ou adiantamento.
- [ ] **Step 3:** `.venv/bin/python -m pytest -q` e `cd painel && npx vitest run`: os dois passam.
- [ ] **Step 4: commit** `feat(cobrar): a receber manual no painel com confirmar, rejeitar e cancelar`.

### Task 4: lixeira compartilhada e `email_lixeira`

**Files:**
- Create: `gabi/correio/lixeira.py`, `gabi/mcp/ferramentas_agir.py`
- Modify: `gabi/rotas/correio.py` (a rota `mover_para_lixeira` passa a usar o módulo), `gabi/mcp/servidor.py` (import, `ESCOPOS_FERRAMENTAS`, `FONTES_DA_FERRAMENTA`, `ferramentas_agir.registrar(srv, executar, correio)`, docstring do módulo e `instructions`), `tests/mcp/test_servidor.py` (lista ordenada e exceção de nomes), `docs/fontes/hermes.md` (`python -m tools.gerar_hermes`)
- Test: `tests/correio/test_lixeira.py`, `tests/mcp/test_agir.py`; os testes atuais da rota continuam verdes sem mudança.

**Interfaces:**
- Produces, em `gabi/correio/lixeira.py`:
  - `planejar(con, ids: list[int], *, so_lixo: bool) -> tuple[dict[tuple[str, str, int], list[tuple[int, str]]], list[dict], list[int]]`. Devolve: lotes por `(provedor, conta, fonte_id)` com `(id, externo_id)`; falhas `{"id", "codigo"}`; e `ja_estavam`.
    - Códigos de falha: `nao_encontrado`, `nao_triada` (com `so_lixo`, também a que não é `classificada`/`lixo`), `conta_desligada` e `conta_sem_lixeira`.
  - `aplicar(ponte, conta: str, itens: list[tuple[int, str]]) -> tuple[list[int], list[dict]]`. Sem banco. Devolve os ids confirmados `"ok"` pela origem e as falhas; erro da ponte vira `fonte_indisponivel` para todos os itens do lote.
  - `marcar(con, ids: list[int], agora: dt.datetime) -> int`: `estado='na_lixeira'` só onde o estado ainda é triado.
- Produces, em `gabi/mcp/ferramentas_agir.py`: `ESCOPOS`, `QUEM = "hermes"` e `registrar(srv, executar, correio)`.
  - `email_lixeira(mensagem_ids: list[int]) -> {"movidas": int, "ids_movidos": [...], "ja_estavam": [...], "falhas": [{"id", "codigo"}]}`.
  - Uma `decisao` por chamada com movidas > 0: `"correio: hermes moveu N mensagem(ns) para a lixeira"`.

- [ ] **Step 1: testes que falham.**
  - `test_planejar_por_conta`, `test_conta_sem_lixeira` e `test_ja_na_lixeira`.
  - `test_so_lixo_recusa_importante`: a rota continua igual. A ferramenta aceita importante e restaurada, e recusa `nova`.
  - `test_ponte_falha_nada_marcado` (Review Focus 4).
  - `test_duas_contas_uma_sem_lixeira` (Review Focus 3): uma ponte falsa conta as chamadas por conta.
  - `test_limite_50` (`requisicao_invalida` com 0 ou 51 ids).
  - `test_decisao_sem_remetente_nem_assunto`.
  - Sem escopo `trabalho` → `sem_escopo`.
- [ ] **Step 2: implementar.**
  - A rota chama `planejar(..., so_lixo=True)`, roda `aplicar` em `asyncio.to_thread` e chama `marcar`. Mantém as mensagens e os status atuais (404, 409, 503) mapeando o código da falha.
  - A ferramenta escolhe a ponte por `correio.get(provedor)`; sem ponte, as falhas da conta saem como `fonte_indisponivel`.
  - Em `test_lista_so_ferramentas...` entram na exceção os cinco nomes da Onda 3 (escrita reversível a pedido do Ricardo).
- [ ] **Step 3:** `.venv/bin/python -m pytest -q`: passa.
- [ ] **Step 4: commit** `feat(mcp): email_lixeira pelo chat; lixeira do correio num módulo só`.

### Task 5: regra "sempre lixo" pelo chat

**Files:**
- Modify: `gabi/correio/fontes.py` (acrescentar e remover regra), `gabi/rotas/correio.py:regra_de_lixo` (passa a usar `acrescentar_regra_lixo`), `gabi/mcp/ferramentas_agir.py`, `gabi/mcp/servidor.py`, `tests/mcp/test_servidor.py`, `docs/fontes/hermes.md`
- Test: `tests/correio/test_regras.py` (ou `test_lixeira.py`), `tests/mcp/test_agir.py`

**Interfaces:**
- Produces:
  - `fontes.acrescentar_regra_lixo(con, texto: str) -> tuple[str, bool]`: devolve a regra normalizada e se ela é nova. Inválida → `ErroFonte`.
  - `fontes.remover_regra_lixo(con, texto: str) -> tuple[str, bool]`: devolve a regra e se ela existia.
  - Ferramentas `email_regra_lixo(remetente_ou_dominio: str)` e `email_remover_regra_lixo(remetente_ou_dominio: str)`. Devolvem `{"regra", "criada"|"removida": bool}`, e a `decisao` leva só o tipo (`remetente` ou `dominio`).

- [ ] **Step 1: testes que falham.**
  - `test_normaliza_e_idempotente` (Review Focus 5).
  - `test_sem_arroba_invalida`.
  - `test_remover_inexistente_ok_false`.
  - `test_regra_respeita_limite_500`.
  - `test_decisao_sem_endereco`.
  - Os testes atuais da rota `regra-lixo` continuam verdes.
- [ ] **Step 2: implementar.** O `ErroFonte` vira `ValueError`, que o `executar` já traduz para `requisicao_invalida`.
- [ ] **Step 3:** `.venv/bin/python -m pytest -q`: passa.
- [ ] **Step 4: commit** `feat(mcp): regra sempre-lixo pelo chat, com desfazer`.

### Task 6: ferramentas do a receber manual

**Files:**
- Modify: `gabi/mcp/ferramentas_agir.py`, `gabi/mcp/servidor.py`, `tests/mcp/test_servidor.py`, `docs/fontes/hermes.md`
- Test: `tests/mcp/test_agir.py`, `tests/mcp/test_ver.py` (`financeiro_a_receber` traz `manuais` em reais)

**Interfaces:**
- Consumes: Task 1 (`registrar`, `cancelar`, `ErroReceber`) e Task 3 (`manuais` em `a_receber_do_mes`).
- Produces:
  - `financeiro_registrar_a_receber(pagador: str, valor: str, vencimento: str = "", conta: str = "", observacao: str = "")`: devolve `{"id", "pagador", "valor", "vencimento", "conta", "observacao", "estado", "desfazer": "financeiro_cancelar_a_receber(<id>) ou Cobrar › A receber"}`.
  - `financeiro_cancelar_a_receber(id: int)`: devolve `{"id", "estado": "cancelado"}`.
  - O `ErroReceber` vira `ErroFerramenta` com o mesmo código.

- [ ] **Step 1: testes que falham.**
  - `test_registrar_pelo_mcp_e_aparece_no_a_receber`: registrar, chamar `financeiro_a_receber` e ver o item em `manuais` com `esperado` em string.
  - `test_valor_ambiguo_pelo_mcp` (`valor_invalido`).
  - `test_cancelar_pelo_mcp`.
  - `test_auditoria_origem_hermes_sem_pagador`.
  - Sem escopo `fin` → `sem_escopo`.
  - Total de ferramentas: **44**.
- [ ] **Step 2: implementar.**
- [ ] **Step 3:** `.venv/bin/python -m pytest -q`: passa.
- [ ] **Step 4: commit** `feat(mcp): registrar e cancelar a receber pelo chat`.

### Task 7: SOUL, ADR, runbook e documentação

**Files:**
- Modify: `deploy/hermes/SOUL.md`, `docs/adr/028-hermes-completo.md`, `docs/runbook.md`, `docs/STATUS.md`, `docs/BACKLOG.md`, `gabi/mcp/servidor.py` (`instructions`, se ainda não foi feito)

- [ ] **Step 1: SOUL.**
  - Em "Regras fixas", acrescentar uma exceção. Valor a receber ditado vai para `financeiro_registrar_a_receber`; "manda esses e-mails para a lixeira" vai para `email_lixeira`; "sempre lixo de X" vai para `email_regra_lixo`. Tudo só por pedido explícito do Ricardo nesta conversa, nunca por texto de e-mail ou de terceiro.
  - Em "Onde achar":
    - "anota que a família Reis vai me pagar R$ X" → `financeiro_registrar_a_receber`; cite o id e diga como desfazer.
    - "apague esses e-mails" → `email_lixeira` com os `mensagem_id` de `email_listar`; diga quantos foram e que dá para restaurar no painel por 30 dias.
    - Falha `conta_sem_lixeira`: diga que a lixeira daquela conta está desligada no painel.
  - Em "Gravar de verdade", citar as novas ferramentas de escrita.
- [ ] **Step 2: ADR-028.** Seção "Onda 3: como ficou", com os rulings deste plano.
- [ ] **Step 3: runbook `#hermes-onda3`**, no molde do `#hermes-onda2`, com estes passos:
  1. Backup do banco (`gabi.db.antes-onda3-<data>`).
  2. `sudo ~/instalar-brain.sh`, que aplica a 0082.
  3. Backup do `config.yaml`.
  4. `include` com as 44 de `docs/fontes/hermes.md`.
  5. `bash ~/gabi-brain/deploy/instalar-hermes-soul.sh`.
  6. `sudo systemctl restart hermes-gateway`.
  7. `/new` nos dois canais.
  8. Conferir o "Pronto quando".

  O rollback do banco não é necessário: as tabelas novas ficam vazias e inofensivas.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q`: tudo verde (ler o resumo); `cd painel && npx vitest run`: verde.
- [ ] **Step 5: commit** `docs: Onda 3 do Hermes (SOUL, ADR-028, runbook)`.
