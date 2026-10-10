-- 0018: edição feita FORA (cofre Obsidian) vira sugestão para o Ricardo decidir; nunca sobrescreve o banco (R1).
create table edicao_externa(
  id integer primary key,
  pessoa_id text not null,
  arquivo text not null,
  texto text not null,
  hash text not null,
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','rejeitada')),
  criado_em text not null,
  decidida_em text,
  unique(pessoa_id, arquivo, hash)
);
