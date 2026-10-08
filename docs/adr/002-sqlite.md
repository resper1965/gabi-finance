# ADR-002 · SQLite (WAL + FTS5) no lugar de Postgres dedicado
- **Contexto:** um usuário, um serviço, ~100 mil lançamentos em 5 anos; o `gabi-fin` já usa SQLite.
- **Decisão:** SQLite 3.45 em WAL, `foreign_keys=ON`, `busy_timeout=5000`, busca por FTS5 (`unicode61 remove_diacritics 2`). SQL padrão; migrações numeradas em `migrations/`.
- **Consequência:** sem Docker, sem serviço novo, backup = copiar um arquivo. Um escritor por vez. Sem permissão por pessoa no banco: saúde vai para arquivo SQLCipher separado (Fase 4, spec §13.1).
- **Quando reverter:** escrita concorrente real, mais de um operador, ou necessidade de segurança por linha. Migrar a Postgres (ADR-001 descreve a conversão).
