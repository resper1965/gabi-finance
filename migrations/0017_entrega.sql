-- 0017: entregas da Linear (somente leitura): o que vence nos projetos. Espelho local; nunca escreve na Linear.
create table entrega(
  id integer primary key,
  externo_id text not null unique,
  identificador text not null,
  titulo text not null,
  projeto text,
  responsavel text,
  prazo text,
  estado text not null,
  atualizado_em text
);
