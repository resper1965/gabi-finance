-- 0088: convites de agenda recebidos (04/11): o evento guarda a resposta do dono, o organizador e a série; envio_proposta aceita o tipo 'convite_resposta'.
-- Spec: docs/superpowers/specs/2026-11-04-convites-agenda-design.md. Sem tabela nova (ADR-023); eventos antigos ficam com as três colunas nulas.
-- SQLite não altera `check`: envio_proposta é recriada com o esquema da 0076 e o tipo ampliado (linhas copiadas).
-- Desfazer: alter table agenda_evento drop column serie_id; alter table agenda_evento drop column organizador_nome; alter table agenda_evento drop column resposta;
--   recriar envio_proposta com o check da 0076 (delete from envio_proposta where tipo='convite_resposta' antes de copiar); delete from schema_versao where nome='0088_convites_agenda.sql';
alter table agenda_evento add column resposta text;
alter table agenda_evento add column organizador_nome text;
alter table agenda_evento add column serie_id text;
create table envio_proposta_nova(
  id integer primary key,
  tipo text not null check (tipo in ('evento','teams_chat','teams_canal','convite_resposta')),
  conta text not null,
  conteudo text not null,
  hash text not null,
  chave text not null unique,
  estado text not null default 'pendente' check (estado in ('pendente','enviando','enviada','recusada','falhou','incerto','vencida')),
  motivo text,
  externo_id text,
  criada_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  vence_em text not null,
  decidida_em text,
  decidida_por text,
  enviada_em text);
insert into envio_proposta_nova(id, tipo, conta, conteudo, hash, chave, estado, motivo, externo_id, criada_em, vence_em, decidida_em, decidida_por, enviada_em)
  select id, tipo, conta, conteudo, hash, chave, estado, motivo, externo_id, criada_em, vence_em, decidida_em, decidida_por, enviada_em from envio_proposta;
drop table envio_proposta;
alter table envio_proposta_nova rename to envio_proposta;
create index envio_proposta_estado on envio_proposta(estado);
