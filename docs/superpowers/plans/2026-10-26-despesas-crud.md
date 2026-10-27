# Despesas (CRUD) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar, mudar (daqui em diante ou só num mês), dispensar um mês, encerrar e excluir despesas fixas e avulsas pelo painel e pelo Hermes, sem deixar ocorrência órfã em A Pagar.

**Architecture:** Um módulo de regras novo, `gabi/dinheiro/despesas.py`, sobre as tabelas que já existem (`compromisso_linha` com séries de versão, `valor_do_mes`, `compromisso`). A API (`gabi/rotas/despesas.py`), o painel (A Pagar + Cadastros › Despesas) e o MCP (`gabi/mcp/ferramentas_despesas.py`) só chamam esse módulo. A geração pula mês dispensado e a gravação da rodada apaga ocorrência não paga que não foi mais gerada.

**Tech Stack:** Python 3 + FastAPI + SQLite (migrações SQL), pytest; painel React + TypeScript + vitest; servidor MCP (`gabi/mcp`).

**Spec:** `docs/superpowers/specs/2026-10-26-despesas-crud-design.md`

## Global Constraints
- Dinheiro em centavos no banco; na API e no MCP sai como string decimal em reais (`formatar`, ex.: `"1500.00"`), nunca float (R7).
- Mês sempre `AAAA-MM`; data `AAAA-MM-DD`. `hoje` = `agora.date()` em America/Sao_Paulo.
- Mudança de valor/dia vale a partir do mês em curso se ele **não** foi pago; se foi, do próximo. Meses passados nunca mudam. `a_partir` explícito vence a regra.
- Encerrar nunca apaga linha do cadastro. Excluir só se a série nunca teve ocorrência paga nem conciliada; senão encerra e devolve `encerrada: true`.
- Ocorrência paga (`estado='pago'`, `valor_do_mes` `pago` ou linha em `conciliacao` com aquele `compromisso_id`) **nunca** é apagada.
- Só ocorrências `origem='planilha'` são mexidas; `fatura:*` e `doc:*` nunca.
- Toda escrita grava uma linha em `decisao` (`quem`, `origem`: `'painel'` pela API, `'hermes'` pelo MCP) e termina com `contas_pagar.atualizar_compromissos(con, hoje, agora)`.
- O Hermes só grava depois de mostrar o que muda e ouvir o sim; nunca por texto de e-mail, Teams ou documento.
- Não mexer no importador da planilha (`repositorio.gravar_leitura`) nem em `/api/v1/cadastros/compromissos` além de delegar a validação.
- Textos do painel e do Hermes em português do Brasil.

## Review Focus
1. **Encerrar antes de começar:** `ultimo_mes` anterior ao `valido_de` da versão (despesa futura) → a versão vira excluída (`excluido_em`), sem erro de validação `valido_ate < valido_de`. Teste em Task 3.
2. **Mudar duas vezes no mesmo mês de início:** a segunda mudança edita a versão `serie-AAAAMM` já criada; não cria outra nem dá erro de sobreposição. Teste em Task 3.
3. **Ocorrência a conferir com vínculo:** despesa encerrada cuja ocorrência está `a_conferir` com linha em `conciliacao` → fica. Teste em Task 4.
4. **Ocorrência de mês antigo em atraso:** encerrar em setembro uma despesa com `x:2026-09` atrasada e não paga a tira de A Pagar (não só os meses da janela). Teste em Task 3.
5. **Fatura e documento:** itens `fatura:*`/`doc:*` não são apagados pelo furo e no painel não ganham o menu de ações. Testes em Task 4 e Task 6.

---

### Task 1: Migração 0085

**Files:**
- Create: `migrations/0085_despesas.sql`
- Test: `tests/dinheiro/test_despesas.py` (novo)

**Interfaces:**
- Produces: `compromisso_linha.tipo` (`'fixa'|'avulsa'`, default `'fixa'`); `valor_do_mes.tipo` aceita `'dispensado'`.

- [ ] **Step 1: Write the failing test**

```python
def test_migracao_tipo_e_dispensado(con):
    con.execute("insert into compromisso_linha(id, nome, extrato, vencimento) values ('x','X','X','dia:5')")
    assert con.execute("select tipo from compromisso_linha where id='x'").fetchone()[0] == "fixa"
    con.execute("insert into valor_do_mes(mes, compromisso, tipo) values ('2026-10','x','dispensado')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("update compromisso_linha set tipo='outra' where id='x'")
```
(fixture `con` = `conectar(tmp_path/"g.db")` + `migrar(c, MIGRACOES)`, como em `tests/dinheiro/test_contas_pagar.py`.)

- [ ] **Step 2: Run and see it fail** — `.venv/bin/pytest tests/dinheiro/test_despesas.py -q` → FAIL (`no such column: tipo`).
- [ ] **Step 3: Write `0085_despesas.sql`** — `alter table compromisso_linha add column tipo ... check`; recriar `valor_do_mes` com `check (tipo in ('valor','pago','dispensado'))` copiando linhas e o índice `valor_do_mes_comp` (modelo: migração 0080).
- [ ] **Step 4: Run** — o teste e `tests/test_esquema.py tests/test_db.py` passam (ler o resumo do pytest, não só o exit code).
- [ ] **Step 5: Commit** — `feat(despesas): migração 0085 (tipo da despesa e mês dispensado)`.

### Task 2: Regras — validar, gravar, criar e listar

**Files:**
- Create: `gabi/dinheiro/despesas.py`
- Modify: `gabi/rotas/cadastros.py` (`Compromissos._validar` e `_gravar` delegam)
- Test: `tests/dinheiro/test_despesas.py`

**Interfaces:**
- Produces (todas em `gabi.dinheiro.despesas`; `LookupError` = não encontrado, `ValueError` = inválido):
  - `validar_linha(con, d: dict, proprio: str | None) -> dict` — o corpo atual de `Compromissos._validar`, levantando `ValueError(motivo)`.
  - `gravar_linha(con, linha: dict, ativo: bool, obs: str | None, inserir: bool, tipo: str = "fixa") -> None` — o corpo atual de `_gravar` + coluna `tipo`.
  - `CAMPOS = {"nome","extrato","apelidos","vencimento","ajuste_dia_util","valor_tipo","valor_padrao","forma","conta","cartao","pix"}`.
  - `criar_fixa(con, agora, quem, origem, campos: dict) -> dict` — id `_slug(nome)` único; `extrato` padrão = `nome`; `valido_de` = mês de `hoje`.
  - `criar_avulsa(con, agora, quem, origem, campos: dict, data: str) -> dict` — `tipo='avulsa'`, `vencimento=f"dia:{dia}"`, `valido_de=valido_ate=data[:7]`, id `f"{slug}-{AAAAMM}"` único.
  - `listar(con, hoje, tipo: str | None = None, situacao: str | None = None) -> list[dict]` — um item por série (`compromissos._serie`): `{"id": serie, "versao_id", "nome", "tipo", "valor", "vencimento", "forma", "valido_de", "valido_ate", "situacao": "ativa"|"encerrada", "proximo_vencimento": "AAAA-MM-DD"|None, "versoes": [{"id","valido_de","valido_ate","valor","vencimento"}]}`; encerrada = última versão com `valido_ate` < mês de `hoje`.
  - `serie_de(con, id_: str) -> list[sqlite3.Row]` — versões não excluídas da série, por `valido_de`; vazia → `LookupError`.
  - Retorno de criar/mudar = o item de `listar` daquela série.
- Consumes: `compromissos._serie`, `planilha._linha`, `cadastros._slug`/`_id_unico` (mover para `despesas` se o import ficar circular).

- [ ] **Step 1: Failing tests** — `test_criar_fixa_gera_em_a_pagar` (criar "Escola", valor `"3000.00"`, `vencimento="dia:6"`, agora 26/10/2026 → `compromisso` tem `escola:2026-10` e `escola:2026-11` com 300000); `test_criar_avulsa_so_um_mes` (data `2026-11-20` → só `*:2026-11`, `tipo='avulsa'`, `valido_de=valido_ate='2026-11'`); `test_criar_invalido` (`vencimento="dia:40"` → `ValueError`); `test_listar_por_tipo_e_situacao`; `test_cadastros_compromissos_continua` (POST `/cadastros/compromissos` com corpo inválido ainda devolve 400 — rodar `tests/rotas/test_cadastros_api.py`).
- [ ] **Step 2: Run and see fail.**
- [ ] **Step 3: Implement** as interfaces acima; decisão: `f"despesa {serie} criada ({tipo})"`.
- [ ] **Step 4: Run** `tests/dinheiro/test_despesas.py tests/rotas/test_cadastros_api.py` → PASS.
- [ ] **Step 5: Commit** — `feat(despesas): criar e listar despesas fixas e avulsas`.

### Task 3: Regras — mudar, mês, encerrar, excluir

**Files:**
- Modify: `gabi/dinheiro/despesas.py`
- Test: `tests/dinheiro/test_despesas.py`

**Interfaces:**
- Produces:
  - `mes_pago(con, serie: str, ym: str) -> bool` — há `compromisso` `"{linha}:{ym}"` de alguma versão com `estado='pago'`, ou `valor_do_mes` `pago`, ou `conciliacao.compromisso_id` = esse id.
  - `mes_inicial(con, serie: str, hoje: dt.date) -> str` — mês de `hoje` se `not mes_pago`, senão o seguinte.
  - `mudar(con, agora, quem, origem, id_, campos: dict, a_partir: str | None = None) -> dict` — mês `m = a_partir or mes_inicial`. Versão vigente em `m`: se `valido_de == m` (ou nunca teve mês pago e `valido_de` ≥ mês de hoje), edita; senão `valido_ate` da vigente = mês anterior a `m` e insere `f"{serie}-{m sem hífen}"` com os campos mesclados e `valido_ate` original. Devolve item de `listar` + `"a_partir": m`, `"nova_versao": bool`.
  - `mudar_mes(con, agora, quem, origem, id_, mes, valor: str | None = None, vencimento: str | None = None) -> dict` — upsert em `valor_do_mes` `tipo='valor'` para a versão vigente em `mes`; ambos `None` → `ValueError`.
  - `dispensar_mes(con, agora, quem, origem, id_, mes) -> dict` / `desfazer_dispensa(...) -> dict` — insere/remove `valor_do_mes` `dispensado`; mês pago → `ValueError("mês já pago")`.
  - `encerrar(con, agora, quem, origem, id_, ultimo_mes: str | None = None) -> dict` — `u = ultimo_mes or mês anterior a mes_inicial`; versões com `valido_de > u` viram `excluido_em`; a que cobre `u` recebe `valido_ate=u`. Devolve `{"id": serie, "ultimo_mes": u}`.
  - `excluir(con, agora, quem, origem, id_) -> dict` — sem mês pago em nenhum mês da série: `excluido_em` em todas → `{"id", "excluida": True, "encerrada": False}`; senão `encerrar` → `{"id", "excluida": False, "encerrada": True, "ultimo_mes"}`.
  - `limpar_nao_pagas(con, serie: str, meses: Callable[[str], bool]) -> int` — apaga `compromisso` da série (`origem='planilha'`, `linha_id` na série) cujo mês satisfaz `meses`, que não esteja paga nem tenha linha em `conciliacao`; apaga o vínculo `manual:` órfão. Usada por `encerrar` (meses > u), `excluir` e `dispensar_mes` (o próprio mês), **em qualquer mês**, não só a janela.

- [ ] **Step 1: Failing tests** (agora = 26/10/2026 12h SP; série "luz" `dia:10`, 20000):
  - `test_mudar_vale_do_mes_em_curso_sem_pagamento` → `a_partir == "2026-10"`, mesma linha editada, `luz:2026-10` com o valor novo.
  - `test_mudar_mes_pago_vale_do_proximo` → com `luz:2026-10` `pago`: nova versão `luz-202611`, `luz.valido_ate == "2026-10"`, `luz:2026-10` mantém 20000.
  - `test_mudar_duas_vezes_mesmo_inicio` (Review Focus 2) → segunda chamada `nova_versao is False`, só 2 versões.
  - `test_mudar_a_partir_explicito` (`"2026-12"`).
  - `test_mudar_mes_so_valor_e_so_data`; `test_dispensar_some_e_desfazer_volta`; `test_dispensar_mes_pago_recusa`.
  - `test_encerrar_tira_nao_pagas_e_mantem_pagas` → `u == "2026-09"`; `luz:2026-10`/`2026-11` somem, `luz:2026-08` paga fica.
  - `test_encerrar_tira_atrasada_antiga` (Review Focus 4) → `encerrar(..., ultimo_mes="2026-08")` apaga `luz:2026-09` atrasada.
  - `test_encerrar_antes_de_comecar` (Review Focus 1) → versão com `valido_de="2026-12"`, `encerrar(ultimo_mes="2026-11")` → excluída, sem `ValueError`.
  - `test_excluir_sem_pagamento_apaga` / `test_excluir_com_pagamento_encerra`.
  - `test_decisao_registrada` (origem e quem).
- [ ] **Step 2: Run and see fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `tests/dinheiro/` → PASS.
- [ ] **Step 5: Commit** — `feat(despesas): mudar daqui em diante, mexer num mês, encerrar e excluir`.

### Task 4: Geração e o furo da rodada

**Files:**
- Modify: `gabi/dinheiro/compromissos.py` (`gerar`, nova `meses_da_rodada`), `gabi/dinheiro/repositorio.py` (`ler_leitura` passa `dispensado`; `gravar_resultado`), `gabi/dinheiro/contas_pagar.py` (`atualizar_compromissos`)
- Test: `tests/dinheiro/test_despesas.py`, `tests/dinheiro/test_pipeline_compromissos.py`

**Interfaces:**
- Produces: `compromissos.meses_da_rodada(hoje: date) -> list[str]` (os 2 `yms` que `gerar` já usa; `gerar` passa a chamá-la). `gravar_resultado(con, comps, resultado, novos_vinculos, agora, meses: list[str] | None = None)` — com `meses`, apaga `compromisso` `origem='planilha'` cujo mês ∈ `meses`, `id` ∉ rodada, `estado<>'pago'` e sem linha em `conciliacao`.
- `gerar` pula `(linha, ym)` com `valor_do_mes` `dispensado` (o `valores` filtrado hoje só pega `tipo=='valor'`; ler os `dispensado` à parte).

- [ ] **Step 1: Failing tests** — `test_rodada_pula_mes_dispensado`; `test_rodada_apaga_orfa_nao_paga` (linha desativada direto no banco → próxima rodada apaga `x:2026-10`); `test_rodada_mantem_paga_e_conciliada` (Review Focus 3: `a_conferir` com `conciliacao` fica); `test_rodada_nao_toca_fatura_nem_documento` (Review Focus 5).
- [ ] **Step 2: Run and see fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `tests/dinheiro/ tests/test_rodada.py tests/golden` → PASS.
- [ ] **Step 5: Commit** — `fix(compromissos): rodada tira de A Pagar o que não é mais gerado e não foi pago`.

### Task 5: API `/api/v1/despesas` e A Pagar com `linha_id`/`mes`/`tipo`

**Files:**
- Create: `gabi/rotas/despesas.py`
- Modify: `gabi/api.py` (include_router), `gabi/dinheiro/contas_pagar.py` (`contas_a_pagar` traz `linha_id`, `mes`, `tipo`; `None` para fatura/documento), `tools/gerar_amostras.py` (amostra `despesas` = `/api/v1/despesas`), `docs/api.md` + `docs/openapi.json` (`python -m tools.gerar_docs_api`), `painel/tests/amostras/*` (`python -m tools.gerar_amostras`)
- Test: `tests/rotas/test_despesas_api.py` (novo), `tests/dinheiro/test_contas_pagar.py`

**Interfaces:**
- Rotas (prefixo `/api/v1`, `exigir("boss")`, `quem = ident.login`, `origem='painel'`; `LookupError`→404 `nao_encontrado`, `ValueError`→400 `requisicao_invalida`):
  - `GET /despesas?tipo=&situacao=` → `envelope(con, {"itens": listar(...)})`
  - `POST /despesas` corpo `{"tipo": "fixa"|"avulsa", "data"?: "AAAA-MM-DD", ...CAMPOS}` (valor em `valor_padrao`, reais string)
  - `PATCH /despesas/{id}` corpo `{...CAMPOS, "a_partir"?}`
  - `POST /despesas/{id}/mes/{mes}` `{"valor"?, "vencimento"?}`; `POST` e `DELETE /despesas/{id}/mes/{mes}/dispensar`
  - `POST /despesas/{id}/encerrar` `{"ultimo_mes"?}`; `DELETE /despesas/{id}`
- Item de `/contas-pagar` ganha `linha_id`, `mes`, `tipo`.

- [ ] **Step 1: Failing tests** — um por rota (status e efeito em `/contas-pagar`), 404 e 400, `test_vip_nao_acessa` (403), `test_a_pagar_traz_linha_e_mes` (e `None` para `fatura:*`).
- [ ] **Step 2: Run and see fail.**
- [ ] **Step 3: Implement**; regenerar docs e amostras.
- [ ] **Step 4: Run** `tests/rotas tests/test_docs_api.py tests/test_amostras_painel.py tests/dinheiro/test_contas_pagar.py` → PASS.
- [ ] **Step 5: Commit** — `feat(despesas): API de despesas e A Pagar com a despesa de cada item`.

### Task 6: Painel — ações em Caixa › A Pagar

**Files:**
- Modify: `painel/src/telas/Caixa/APagar.tsx`, `painel/tests/apiFalsa.ts` (rota `/\/despesas/` → `despesas`)
- Create: `painel/src/telas/Caixa/DespesaForm.tsx` (formulário reutilizado em Cadastros)
- Test: `painel/tests/despesas.test.tsx` (novo)

**Interfaces:**
- `DespesaForm({ modo: "nova" | "daqui" | "mes", item?: Item, aoSalvar: () => void })` — "nova": Fixa/Avulsa, nome, valor, dia (fixa) ou data (avulsa), forma; "daqui": valor, dia, "a partir de" (mês, opcional); "mes": valor, data.
- Em cada item com `linha_id` (não em `pagas`): botão "Ações" com "Editar este mês", "Dispensar este mês", "Mudar daqui em diante", "Encerrar". Dispensar e Encerrar mostram toast com "Desfazer" (Dispensar → `DELETE .../dispensar`; Encerrar → só o aviso "Desfeito em Cadastros › Despesas"). Botão "+ despesa" no topo.

- [ ] **Step 1: Failing tests** — `dispensar chama POST /despesas/{linha}/mes/{mes}/dispensar`; `encerrar chama POST /despesas/{linha}/encerrar`; `mudar daqui em diante manda valor_padrao e a_partir`; `+ despesa avulsa manda tipo e data`; `fatura não tem menu de ações` (Review Focus 5).
- [ ] **Step 2: Run** `cd painel && npx vitest run tests/despesas.test.tsx` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx vitest run` e `npm run build` → PASS.
- [ ] **Step 5: Commit** — `feat(painel): ações de despesa em A Pagar`.

### Task 7: Painel — Cadastros › Despesas

**Files:**
- Create: `painel/src/telas/CadastrosDespesas.tsx`
- Modify: `painel/src/App.tsx` (aba `despesas`), `painel/src/navegacao.ts` (aba `["despesas", "Despesas", "O que eu pago todo mês, e o que é uma vez só?"]` em Cadastros)
- Test: `painel/tests/despesas.test.tsx`, `painel/tests/navegacao.test.tsx`

**Interfaces:** consome `GET /despesas` e as rotas da Task 5; `DespesaForm` da Task 6.
- Abas Fixas / Avulsas / Encerradas; por linha: editar (`modo="daqui"`), encerrar, excluir (com confirmação; se a resposta trouxer `encerrada: true`, toast "Já teve pagamento: foi encerrada, não excluída"); histórico de versões expansível.

- [ ] **Step 1: Failing tests** — abas filtram; excluir mostra o aviso de encerrada; navegação tem a aba.
- [ ] **Step 2–4:** fail → implement → `npx vitest run` + `npm run build` PASS.
- [ ] **Step 5: Commit** — `feat(painel): Cadastros › Despesas`.

### Task 8: Hermes — ferramentas MCP, SOUL e ADR

**Files:**
- Create: `gabi/mcp/ferramentas_despesas.py`, `docs/adr/032-despesas-crud.md`
- Modify: `gabi/mcp/servidor.py` (ESCOPOS, `FONTES_DA_FERRAMENTA` com `()`, `registrar`, texto de instruções da linha das escritas), `tests/mcp/test_servidor.py` (listas), `docs/fontes/hermes.md` (include), `deploy/hermes/SOUL.md`, `docs/runbook.md` (seção `#despesas`), `docs/STATUS.md`, `docs/BACKLOG.md`, `docs/api.md` (regenerar)
- Test: `tests/mcp/test_despesas_mcp.py` (novo), `tests/mcp/test_hermes.py`, `tests/mcp/test_confiabilidade.py`

**Interfaces:**
- Escopo `fin` para todas; `quem='hermes'`, `origem='hermes'`; `despesa` = id ou nome (id exato > nome exato > prefixo > trecho, como `financeiro_marcar_reembolso`); 0 → `ErroFerramenta("nao_encontrado")`, 2+ → `ErroFerramenta("ambiguo", opções)`. Valor ditado com `receber_manual.valor_ditado` → `formatar`.
  - `despesas_listar(texto: str = "", situacao: str = "ativa") -> dict`
  - `despesa_criar(nome: str, valor: str, dia: int = 0, data: str = "", forma: str = "") -> dict` — `data` ⇒ avulsa; senão `dia` 1–31 obrigatório.
  - `despesa_mudar(despesa: str, valor: str = "", dia: int = 0, a_partir: str = "") -> dict`
  - `despesa_mes(despesa: str, mes: str, valor: str = "", vencimento: str = "", dispensar: bool = False) -> dict`
  - `despesa_encerrar(despesa: str, ultimo_mes: str = "") -> dict`
  - `despesa_excluir(despesa: str) -> dict`
  - Cada retorno traz `desfazer` (texto).
- SOUL: na linha de exceções e na lista "→" acrescentar: "não vou mais pagar X" → `despesa_encerrar`; "este mês o X é 500" / "pula o X este mês" → `despesa_mes`; "a partir de dezembro o X sobe" → `despesa_mudar`; "nova conta / paguei uma vez" → `despesa_criar`; mostrar antes e gravar depois do sim.

- [ ] **Step 1: Failing tests** — cada ferramenta grava e registra `decisao` origem `hermes`; `ambiguo`; `nao_encontrado`; valor `"1.500"` recusado; escopo sem `fin` recusa; listas oficiais (`test_servidor`, `test_hermes`) contêm as 6.
- [ ] **Step 2: Run and see fail.**
- [ ] **Step 3: Implement**; escrever ADR-032 (contexto, as 4 decisões da spec, consequências, desfazer); runbook `#despesas` com backup `gabi.db.antes-despesas-<data>`, `sudo ~/instalar-brain.sh` (migração 0085), backup `config.yaml.bak-antes-despesas`, include das 6 ferramentas, `deploy/instalar-hermes-soul.sh`, restart `hermes-gateway`, `/new` nos dois canais.
- [ ] **Step 4: Run a suíte inteira** `.venv/bin/pytest -q` e `cd painel && npx vitest run` — ler o resumo (número de passed/failed), não o exit code.
- [ ] **Step 5: Commit** — `feat(hermes): ferramentas de despesas (ADR-032)`.
