# ADR-001 · IDs inteiros e texto em vez de uuid v7
- **Contexto:** o handoff pede uuid v7 e `numeric(14,2)` (Postgres). Escolhemos SQLite (ADR-002).
- **Decisão:** `INTEGER PRIMARY KEY` nas tabelas novas; ID externo em `externo_id UNIQUE`. Dinheiro em **centavos inteiros** (`*_centavos`); na API, string decimal `"1234.56"`. Cadastros do staging mantêm o ID de texto de origem (`p1`, `e1`).
- **Consequência:** sem erro de ponto flutuante; sem extensão de banco; ordenação por ID = ordem de criação.
- **Quando reverter:** se migrar para Postgres, converter `INTEGER` para `numeric(14,2)` pela migração; os centavos viram `valor/100`.
