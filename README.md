# gabi-finance

Serviço **só financeiro** da Gabi, a assistente pessoal agêntica do Ricardo Esper: extratos e saldos via Open Finance (mcp.ai), conciliação, contas a pagar e compromissos, projeção de caixa, gastos por pessoa e por cartão, assinaturas, despesas por empresa, notas fiscais e valores a receber (Nibo) — com **painel web** (atrás do Tailscale) e **servidor MCP** para o agente de conversa (Hermes, no Telegram e no WhatsApp).

> **Estado (17/11/2026): em construção.** Este repositório nasceu como cópia do `gabi-brain` (com todo o histórico) e está sendo **cortado** até ficar só com o financeiro, na branch `corte`. A documentação completa (arquitetura, módulos, tabelas, ferramentas MCP, telas, operação e virada) entra ao fim do corte — ver o plano.

## Por que existe

O `gabi-brain` concentrava tudo: dinheiro, agenda, e-mail, Teams, família, documentos, projetos. Na reescrita da Gabi (projeto **esper-brain**), o contexto da vida passa a viver num **segundo cérebro em markdown** (`resper1965/esper-brain`), e só o que precisa de banco e de conta exata fica como serviço — o financeiro. Este repositório é a **etapa 2** dessa reescrita.

| Etapa | O quê | Estado |
|---|---|---|
| 1 | Migrar o contexto (família, pessoas, projetos, empresas) para o `esper-brain` | concluída |
| 2 | Quebrar o `gabi-brain`: nasce o **gabi-finance** | em andamento |
| 3 | Migrar a VPS: coletor, digestão e Hermes lendo o `esper-brain` | a fazer |
| 4 | Testar GBrain e Honcho sobre o markdown | a fazer |

## Como funciona (resumo)

```
mcp.ai (Open Finance) ─┐
Nibo (NFS-e)  ─────────┤  ponte (único processo com rede e token)
                       ▼
            gabi-finance: SQLite (WAL)
     ┌───────────────┼────────────────┐
     ▼               ▼                ▼
 painel web      MCP gabi_finance    timers (extratos, saldos, notas,
 (Tailscale)     (Hermes)            avisos e resumo financeiro no Telegram)
```

- **A Gabi sugere, o Ricardo decide.** Nada paga, envia ou apaga sozinho.
- **Pessoas:** os gastos são atribuídos por pessoa (portador do cartão, "para quem"); esposa e filhas têm cartão da conta do Ricardo.
- **Segurança:** só o serviço de fontes tem rede e token; a API escuta num socket Unix, exposta só pelo `tailscale serve`.

## Documentos

- Desenho: [`docs/superpowers/specs/2026-11-17-gabi-finance-design.md`](docs/superpowers/specs/2026-11-17-gabi-finance-design.md)
- Plano do corte: [`docs/superpowers/plans/2026-11-17-gabi-finance-corte.md`](docs/superpowers/plans/2026-11-17-gabi-finance-corte.md) (na branch `corte`)
- Desenho geral da reescrita: `resper1965/esper-brain`, `docs/superpowers/specs/2026-11-17-esper-brain-design.md`

## Desenvolvimento

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock pytest ruff
.venv/bin/python -m pytest -q
.venv/bin/ruff check gabi tools tests
cd painel && npm ci && npx vitest run && npm run build
```
