# Gastadores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** campo "quem gastou" (portador do cartão), separado de "para quem", preenchido pelo cartão quando há um portador e indicado pelo Ricardo nos compartilhados.

**Architecture:** migração 0084 (colunas no lançamento + tabela de "sempre assim" de gastador); módulo `gabi/dinheiro/gastador.py` preenche ao fim da captura e no histórico; API/painel/MCP leem e gravam pelo mesmo módulo.

**Tech Stack:** Python 3 + SQLite + FastAPI; React/TS (Vite, Vitest); MCP (FastMCP).

**Spec:** `docs/superpowers/specs/2026-10-26-gastadores-design.md`

## Global Constraints
- Gastador só pode ser portador da conta do lançamento (`conta.usuarios`); nada de lista de pessoas no código.
- Compartilhado (2+ portadores) sem indicação/regra = vazio ("a indicar"); nunca deduzir pelo histórico nem pelo `para_quem`.
- `gastador_origem` ∈ {'cartao','voce','regra'}; 'voce' e 'regra' nunca são sobrescritos pelo preenchimento automático.
- Conta corrente: usuário único da conta; sem usuário, pessoa `papel='titular'`.
- Hermes grava direto depois de mostrar e ouvir o sim; registra `decisao` origem 'hermes'.

## Review Focus
- Ricardo tira um portador do cartão em Cadastros depois de indicar → a indicação 'voce' continua (não some), e o automático 'cartao' é recalculado. Teste em Task 1.
- Cartão vira de 1 para 2 portadores (Bradesco hoje) → o que era 'cartao' do portador único volta a "a indicar". Teste em Task 1.
- Indicar pessoa que não é portadora daquela conta pelo lote misturando cartões → 400 e nada gravado (atômico). Teste em Task 2.
- Regra "sempre assim" de uma loja num cartão não vaza para a mesma loja em outro cartão. Teste em Task 1.
- Lançamento de entrada/estorno não aparece como "a indicar". Teste em Task 2.

---

### Task 1: migração e preenchimento

**Files:**
- Create: `migrations/0084_gastador.sql`, `gabi/dinheiro/gastador.py`, `tests/dinheiro/test_gastador.py`
- Modify: `gabi/dinheiro/captura.py` (junto do `nao_gasto.reaplicar`, mesma transação), `tests/dinheiro/test_captura.py`

**Interfaces:**
- Produces: `portadores(con, conta_id: int) -> list[str]`; `preencher(con, ids: list[int] | None = None) -> dict[str, int]` (contagem por origem resultante + 'a_indicar'); `indicar(con, ids: list[int], pessoa: str | None, regra: bool = False) -> None` (ValueError `nao_portador` / LookupError); migração cria `lancamento.gastador_id text references pessoa(id)`, `lancamento.gastador_origem text check (... in ('cartao','voce','regra'))`, `gastador_regra(id integer primary key, conta_id integer not null references conta(id), estabelecimento text not null, pessoa_id text not null references pessoa(id), criado_em text not null, unique(conta_id, estabelecimento))`.

- [ ] Testes: `test_um_portador_vem_do_cartao`, `test_compartilhado_fica_a_indicar`, `test_conta_corrente_e_do_titular`, `test_indicacao_do_ricardo_nao_e_sobrescrita`, `test_um_para_dois_portadores_volta_a_indicar`, `test_tirar_portador_mantem_indicacao_voce`, `test_regra_da_loja_so_no_mesmo_cartao`, `test_indicar_nao_portador_recusa`; captura: `test_captura_preenche_gastador_e_mantem_indicacao`.
- [ ] Implementar; rodar `pytest tests/dinheiro -q`; commit.

### Task 2: API

**Files:** Modify `gabi/rotas/dinheiro.py` (EDITAVEIS + `gastador_id`, lote atômico com `criar_regra` → `indicar(..., regra=True)`), `gabi/dinheiro/consultas.py` (`gastador`, `portadores` no item; filtro `gastador`; `pendente=gastador` = cartão com 2+ portadores, gasto, saída, gastador nulo; `agrupar(por="gastador")` com "(a indicar)"), `gabi/rotas/gastos.py` (aceitar `por=gastador`), `gabi/rotas/contagens.py` (menu gastos soma a indicar). Test: `tests/rotas/test_dinheiro_api.py`, `tests/rotas/test_gastos_api.py`, `tests/rotas/test_contagens.py`.

- [ ] Testes: indicar via PATCH (origem voce), null volta ao automático, lote com não portador → 400 sem gravar nada, `pendente=gastador` não traz entrada nem conta corrente, agrupado por gastador com "(a indicar)", contador.
- [ ] Implementar; regenerar `tools.gerar_docs_api` e `tools.gerar_amostras`; commit.

### Task 3: painel

**Files:** Modify `painel/src/telas/Gastos/Lancamentos.tsx` (filtro "Quem gastou: a indicar"; botões só com `portadores`; link "sempre <pessoa> em <loja>"), `painel/src/telas/Gastos/Cartoes.tsx` (coluna e lote "Quem gastou"), `painel/src/telas/Gastos/ParaOndeVai.tsx` (vista "Quem gastou" ao lado de "Para quem foi"). Test: `painel/tests/gastadores.test.tsx`.

- [ ] Testes: botões = portadores do cartão; tocar envia `{gastador_id}`; vista Quem gastou chama `por=gastador`.
- [ ] `npx tsc --noEmit`, `npx vitest run`; commit.

### Task 4: Hermes

**Files:** Modify `gabi/mcp/ferramentas_agir.py` (`financeiro_indicar_gastador(lancamento_ids: list[int], pessoa: str)`; erro `nao_portador`), `gabi/mcp/servidor.py` (escopos, fontes, instruções; `financeiro_lancamentos` com `gastador` e `pendente`; `financeiro_para_onde_vai` aceita `gastador`), `deploy/hermes/SOUL.md`, `docs/fontes/hermes.md` (via `tools.gerar_hermes`), `tools/auditar_promessas.py`, testes MCP.

- [ ] Testes: indicar e auditoria, `nao_portador`, sem escopo `fin`, lista do Hermes.
- [ ] Commit; ADR-030 + runbook; suíte completa.

### Instalação (depois do ok)
Merge, `instalar-brain.sh`, Bradesco `usuarios=["ricardo","louise"]`, `python -m gabi.dinheiro.gastador --banco ...` (contagens), Hermes include + SOUL + restart; Ricardo dá `/new`.
