# Pendências do Hermes (06/11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Fechar as pendências do handoff de 06/11 que não dependem do Ricardo e deixar registrado o que depende.

**Architecture:** Só texto: `deploy/hermes/SOUL.md` (regras de resposta) e `docs/BACKLOG.md`. Nenhuma mudança em código do brain, nada instalado, sem push.

**Tech Stack:** Markdown; pytest (`tests/mcp/test_hermes.py`, `tests/mcp/test_confiabilidade.py` leem o SOUL).

**Spec:** `docs/superpowers/plans/2026-11-06-hermes-enxuto-achados.md` (achados) e `docs/BACKLOG.md` (HE4, PJ1).

## Global Constraints
- Nada instala nem faz merge/push sem ok explícito do Ricardo; resumo curto; privacidade é dele.
- `formatar()` em `gabi/dinheiro/valor.py` já devolve o sinal ("-1280.13"): o "--R$" nasce no texto do Hermes, então a correção é no SOUL.

## Review Focus
- Valor negativo (saldo, fatura) vira "-R$ 1.280,13" com um sinal só.
- Atividade sem data: o Hermes não promete lembrete.
- Conflito "(sem título)": existe no banco (eventos da ness sem título), não é bug.

### Task 1: SOUL, formato de negativo e promessa de lembrete
**Files:** Modify `deploy/hermes/SOUL.md`; Test `tests/mcp/test_hermes.py`, `tests/mcp/test_confiabilidade.py`

- [ ] Step 1: Na seção "Formato das mensagens", acrescentar: valor negativo escreve-se `-R$ 1.280,13` (um sinal só, antes do R$; o dado do brain já traz o "-").
- [ ] Step 2: Na regra de `atividade_criar` e `projeto_criar`, acrescentar: sem data (`vence` vazio) não diga que vai lembrar; diga que ficou na lista e pergunte se quer data.
- [ ] Step 3: Rodar `.venv/bin/python -m pytest tests/mcp/test_hermes.py tests/mcp/test_confiabilidade.py -q` e ler o resumo. Esperado: tudo passa.

### Task 2: BACKLOG e commit
**Files:** Modify `docs/BACKLOG.md`

- [ ] Step 1: Em HE4/PJ1 registrar: "--R$" corrigido no SOUL (falta instalar); minor do `vence_em` tratado no SOUL, sem mudar código; conflito "(sem título)" é real (eventos da ness sem título no banco); S2 segue pendente do áudio do Ricardo.
- [ ] Step 2: Commit na main (SOUL, BACKLOG, PLANO-DEFINITIVO, achados, este plano). Sem push.

### Fora do plano (dependem do Ricardo)
- S2: um áudio curto no Telegram para medir a transcrição duplicada.
- Instalar o SOUL novo (cópia + `/new`): só com ok dele.
- Teams: ideia, spec própria só se ele quiser.
