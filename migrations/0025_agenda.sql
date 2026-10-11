-- 0025: agenda (somente leitura) como fonte própria, separada do e-mail (spec 2026-10-11-agenda-design).
-- A 0024 fica reservada aos exames. Tempo em UTC + dia local pré-calculado; nada de e-mail de participante nem de local (só a contagem).
create table agenda_fonte(
  id integer primary key,
  conta text not null,
  provedor text not null check (provedor in ('google','graph')),
  calendario_id text not null default 'primary',
  nome text,
  estado text not null default 'a_decidir' check (estado in ('a_decidir','sim','nao')),
  auth text not null default 'oauth' check (auth in ('oauth','delegacao')),
  sync_token text,
  sincronizada_em text,
  recarga_em text,
  ultimo_erro text,
  unique(conta, calendario_id));

create table agenda_evento(
  id integer primary key,
  fonte_id integer not null references agenda_fonte(id),
  externo_id text not null,
  inicio_utc text not null,
  fim_utc text not null,
  dia_local text not null,
  dia_fim_local text not null,
  dia_inteiro integer not null default 0,
  titulo text,
  link_reuniao text,
  participantes_qtd integer not null default 0,
  status text,
  etag text,
  atualizado_origem text,
  privado integer not null default 0,
  unique(fonte_id, externo_id));
create index agenda_evento_dia on agenda_evento(dia_local);
create index agenda_evento_inicio on agenda_evento(inicio_utc);
