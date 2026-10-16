-- EV5: quanto cada chamada ao MCP levou (ms), para o painel de qualidade. Nulo nas chamadas antigas e nas recusadas antes de executar.
alter table chamada_mcp add column duracao_ms integer;
