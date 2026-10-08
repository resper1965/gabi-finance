# ADR-004 · Sem fila Procrastinate, sem data lake Parquet/DuckDB, sem pgvector, sem sops+age
- **Contexto:** o handoff os previa; o `gabi-fin` já roda com timers `systemd` e o volume é pequeno (spec §12).
- **Decisão:** rodadas por timers `systemd` + tabela `rodada`; bruto em JSONL comprimido imutável (`gravar_bruto`); busca de texto por FTS5; credenciais em `/etc/gabi/brain.env` (600), configuradas pelo Ricardo.
- **Consequência:** menos peças para operar; o bruto permite reconstruir o banco do zero.
- **Quando reverter:** rodadas concorrentes problemáticas (fila); análise de rumo pesada (DuckDB, Fase 4); busca textual insuficiente (vetores); mais de um operador (cofre).
