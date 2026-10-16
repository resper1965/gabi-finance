# MC1 · Ferramentas MCP de análise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor ao Hermes, somente leitura e com escopo `fin`, as análises que hoje só o painel usa: recorrentes, previsão, vazamentos e rumo.

**Architecture:** quatro ferramentas novas em `gabi/mcp/servidor.py` seguindo o molde de `financeiro_para_onde_vai` (`executar(nome, f)`), cada uma chamando `analise.*` com `FonteAnalise(con)` ou `rumo.rumo_mensal`. Registradas em `ESCOPOS_FERRAMENTAS`; a lista do Hermes é regerada por `tools/gerar_hermes.py`. `financeiro_assinaturas` do backlog não vira ferramenta própria: as assinaturas já saem dentro de `financeiro_vazamentos` (`out['assinaturas']`).

**Tech Stack:** Python, `mcp` MCPServer, pytest, Starlette TestClient.

**Spec:** `docs/BACKLOG.md` item MC1 (listadas, escopo `fin`, testes de "nenhuma destrutiva").

## Global Constraints
- Só leitura (R1/R2/R13): nenhuma ferramenta que envie, pague, apague ou aprove.
- Escopo `fin`; toda chamada vira `chamada_mcp` (já feito por `executar`).
- Valores devolvidos em reais já formatados pelas análises; `rumo` em centavos deve sair com `formatar`.
- Não mexer em `~/.hermes/config.yaml` nem reiniciar o gateway: é passo do dono (runbook).

## Review Focus
- Parâmetro inválido (`meses=0`, `dias=9999`, `ano` absurdo) devolve `requisicao_invalida`, não erro interno (testes na Task 1).
- Banco sem saldo: `previsao` usa `ultimo_snapshot` vazio; não pode quebrar (teste na Task 1).
- Token sem escopo `fin` não enxerga as novas (teste existente por escopo, estender na Task 1).

---
### Task 1: Quatro ferramentas e documentação

**Files:**
- Modify: `gabi/mcp/servidor.py` (imports, `ESCOPOS_FERRAMENTAS`, quatro `@srv.tool()` após `financeiro_para_onde_vai`)
- Test: `tests/mcp/test_servidor.py` (`LEITURA_FASE1`) e novo `tests/mcp/test_ferramentas_analise.py`
- Regenerar: `docs/fontes/hermes.md` via `python -m tools.gerar_hermes`

**Interfaces:**
- Consumes: `analise.recorrentes(fonte, 'caixa', hoje)`, `analise.previsao(fonte, dias, hoje=hoje)`, `analise.vazamentos(fonte, meses, hoje)`, `rumo.rumo_mensal(con, ano) -> list[LinhaRumo]`, `FonteAnalise(con)`, `ferramentas_trab._inteiro(valor, min, max, nome)`.
- Produces: tools `financeiro_recorrentes(sentido: str | None = None)`, `financeiro_previsao(dias: int = 30)` (1–90), `financeiro_vazamentos(meses: int = 3)` (1–12), `financeiro_rumo(ano: int | None = None)`; as quatro com escopo `fin`.

- [ ] **Step 1: Failing tests.** No arquivo novo, reutilizar o fixture `banco`/cliente de `test_servidor.py` (importar ou copiar o helper de chamada): `test_listadas_com_escopo_fin` (as 4 em `ferramentas_do_token(["fin"])`, ausentes em `["docs"]`), `test_recorrentes_devolve_lista` (banco com 4 meses de "ACADEMIA" −200 → item com `valor_medio` 200), `test_previsao_sem_saldo_nao_quebra`, `test_dias_invalido_e_requisicao_invalida` (`dias=9999` → `erro == "requisicao_invalida"`), `test_vazamentos_traz_chaves` (`assinaturas`, `aumentos`), `test_rumo_formata_valores`. Em `test_servidor.py` somar as quatro a `LEITURA_FASE1`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/mcp -q` → novos FALHAM.
- [ ] **Step 3:** Implementar as quatro ferramentas no molde de `financeiro_para_onde_vai`; `sentido` filtra `entrada|saida` e rejeita outro valor com `ValueError`; `rumo` converte centavos com `formatar`; ano padrão `agora.year`. Acrescentar as quatro em `ESCOPOS_FERRAMENTAS` com "fin".
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/mcp -q` → PASS; `.venv/bin/python -m pytest -q` → suíte inteira, ler o resumo.
- [ ] **Step 5:** `.venv/bin/python -m tools.gerar_hermes` e conferir que o diff de `docs/fontes/hermes.md` só soma as quatro; acrescentar no `docs/runbook.md` o passo do dono (incluir as quatro no `tools.include` e reiniciar `hermes-gateway`).
- [ ] **Step 6: Commit** `git add gabi/mcp/servidor.py tests/mcp docs/fontes/hermes.md docs/runbook.md docs/BACKLOG.md && git commit -m "MC1: ferramentas MCP de análise (recorrentes, previsão, vazamentos, rumo)"` (com Co-Authored-By).
