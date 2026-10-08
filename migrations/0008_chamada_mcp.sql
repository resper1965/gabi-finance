-- 0008: log de toda chamada ao servidor MCP (R4). token_id nulo = requisição que nem autenticou.
create table chamada_mcp(
  id integer primary key autoincrement, quando text not null,
  token_id integer references token_agente(id),
  ferramenta text, escopo text,
  status text not null check (status in ('ok','sem_escopo','erro','nao_autenticado')));
create index chamada_mcp_quando on chamada_mcp(quando);
