# ADR-010 — Donos padrão e a origem `fonte`

**Contexto.** O Ricardo é caixa de várias pessoas; decidir lançamento a lançamento não escala. Em 09–10/10/2026 ele ditou padrões por cartão, categoria, compromisso, loja e responsável.

**Decisão.** Os padrões vivem em `seeds/donos-padrao.json` (dado editável, nunca chumbado no código) e são aplicados por `tools/semear_donos.py` (idempotente, auditado). Precedência: dono do cartão > categoria; regra por estabelecimento > padrão do cadastro. Padrão de cadastro grava origem `fonte`, que qualquer regra por loja pode sobrescrever; `voce` e `regra` nunca são sobrescritos. Entre regras, a primeira ativa que casa vale e uma regra nova não completa lançamento já tomado por outra.

**Consequência.** 96% dos lançamentos já têm dono; o sistema só pergunta a exceção. Mudar um padrão é editar o seed e reaplicar (`sudo ~/aplicar-donos.sh`).

**Quando reverter.** Se a cauda longa sem dono (hoje 145) crescer mais rápido que as regras, ou se o Ricardo deixar de ser caixa dessas pessoas.
