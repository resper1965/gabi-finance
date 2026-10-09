-- 0009: Fase 2 (Cobrar) — comprovantes do Paperless e vínculo proposto/confirmado com lançamentos (R1: a Gabi propõe, o Ricardo confirma).
create table comprovante(
  id integer primary key,
  paperless_id integer not null unique,
  tipo text not null,
  valor_centavos integer not null,
  data text not null,
  cnpj text,
  pessoa_id text references pessoa(id));

create table comprovante_vinculo(
  id integer primary key,
  comprovante_id integer not null references comprovante(id),
  lancamento_id integer not null references lancamento(id),
  confianca real not null check (confianca >= 0 and confianca <= 1),
  motivo text not null,
  estado text not null default 'proposto' check (estado in ('proposto','confirmado','rejeitado')),
  criado_em text not null, decidido_em text, decidido_por text,
  unique (comprovante_id, lancamento_id));
create index comprovante_vinculo_lancamento on comprovante_vinculo(lancamento_id, estado);
