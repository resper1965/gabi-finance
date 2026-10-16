# AR8 · Desvio do normal na agenda financeira Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar na mensagem diária da agenda financeira os recorrentes cujo valor deste mês foge do normal de meses anteriores.

**Architecture:** `gabi/dinheiro/desvio.py` (já escrito, com 9 testes, não commitado) calcula os avisos a partir de `FonteAnalise`. `agenda_financeira._diaria` ganha uma função irmã de `_a_receber_atrasado` que chama `fora_do_normal` e formata no máximo 3 linhas. Só leitura (R1/R2).

**Tech Stack:** Python, pytest, SQLite (`gabi.dinheiro.repositorio.FonteAnalise`).

**Spec:** `docs/BACKLOG.md` item AR8 (valor fora de ±2 desvios, aviso `fora_do_normal`). Estender "cobrada depois de cancelar" fica fora desta rodada.

## Global Constraints
- R1 a Gabi sugere, R2 nenhum envio externo; mensagem só informa.
- `analise.recorrentes` é protegido por golden: não alterar.
- Dado nunca chumbado; "hoje" sempre data de Brasília (`hoje` vem de `montar`).

## Review Focus
- Banco sem lançamentos: a diária não pode quebrar nem ganhar linha (teste na Task 1).
- Mais de 3 avisos: truncar e dizer "+N" (teste na Task 1).
- Conta não liberada não entra no normal: `FonteAnalise.visao` não filtra por `estado`; confirmar se o aviso de conta `a_decidir` pode aparecer e registrar o achado no relatório (verificação manual na Task 1, Step 5).

---
### Task 1: Linha "fora do normal" na diária

**Files:**
- Modify: `gabi/dinheiro/agenda_financeira.py` (import e `_diaria`, após `_a_receber_atrasado`)
- Test: `tests/dinheiro/test_agenda_financeira.py`
- Commit também: `gabi/dinheiro/desvio.py`, `tests/dinheiro/test_desvio.py`

**Interfaces:**
- Consumes: `desvio.fora_do_normal(fonte, hoje) -> list[{"descricao","sentido","valor","normal","motivo"}]`; `repositorio.FonteAnalise(con)`.
- Produces: `_fora_do_normal(con, hoje: dt.date) -> list[str]` (privada), até 3 linhas + "+N" opcional.

- [ ] **Step 1: Failing tests** em `test_agenda_financeira.py`: `test_diaria_traz_fora_do_normal` (energia −300×5 meses e −900 em 2026-10; assert `"Fora do normal: ENERGIA"` em alguma linha e `"R$ 900"`/`"300"` na mesma), `test_diaria_sem_historico_nao_ganha_linha` (banco vazio: nenhuma linha contém "Fora do normal"), `test_diaria_limita_a_tres_avisos` (4 séries desviantes: 3 linhas + "+1 fora do normal"). Reaproveitar o fixture `con` e o helper de lançamentos já existentes no arquivo.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/dinheiro/test_agenda_financeira.py -q` → os 3 novos FALHAM.
- [ ] **Step 3:** Implementar `_fora_do_normal(con, hoje) -> list[str]` em `agenda_financeira.py`: formato `• ⚠️ Fora do normal: {descricao} {_brl(valor_centavos)} (normal ~{_brl(normal_centavos)})`, valores via `round(x*100)`; limite 3 e linha `• +N fora do normal`. Chamar em `_diaria` logo após `_a_receber_atrasado`.
- [ ] **Step 4:** Mesmo comando → PASS; depois `.venv/bin/python -m pytest -q` → suíte inteira verde (ler o resumo, não o exit code).
- [ ] **Step 5:** Verificar com dado real, só leitura: `.venv/bin/python -c` chamando `fora_do_normal(FonteAnalise(con))` contra uma cópia do banco; anotar no BACKLOG o que apareceu (falso alarme ou não).
- [ ] **Step 6: Commit** `git add gabi/dinheiro/desvio.py tests/dinheiro/test_desvio.py gabi/dinheiro/agenda_financeira.py tests/dinheiro/test_agenda_financeira.py docs/BACKLOG.md && git commit -m "AR8: desvio do normal na agenda financeira"` (com a linha Co-Authored-By).
