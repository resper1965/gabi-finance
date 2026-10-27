-- 0087: projetos (27/10): gestão de projetos conduzida pelo Hermes; atividades ganham projeto, dependência e marco.
-- Spec: docs/superpowers/specs/2026-10-27-projetos-design.md. Datas em ISO (prazo = dia local de Brasília); dinheiro em centavos.
-- Desfazer: drop table projeto_fato; drop table projeto_gasto; drop table anexo; drop table projeto_pessoa;
--   alter table atividade drop column marco; alter table atividade drop column depende_de_id; alter table atividade drop column projeto_id;
--   drop table projeto; delete from schema_versao where nome='0087_projetos.sql';
create table projeto(
  id integer primary key,
  nome text not null,
  objetivo text,
  status text not null default 'ativo' check (status in ('ativo','pausado','concluido','cancelado')),
  prazo text,
  orcamento_centavos integer,
  criado_em text not null,
  encerrado_em text,
  origem text not null);
alter table atividade add column projeto_id integer references projeto(id);
alter table atividade add column depende_de_id integer references atividade(id);
alter table atividade add column marco integer not null default 0;
create index atividade_projeto on atividade(projeto_id);
create table projeto_pessoa(
  id integer primary key,
  projeto_id integer not null references projeto(id),
  nome text not null,
  papel text,
  pessoa_id text references pessoa(id),
  contato text);
create table anexo(
  id integer primary key,
  tipo text not null check (tipo in ('imagem','audio','documento')),
  arquivo text,
  sha256 text unique,
  paperless_id integer,
  transcricao text,
  recebido_em text not null,
  projeto_id integer references projeto(id));
create table projeto_gasto(
  id integer primary key,
  projeto_id integer not null references projeto(id),
  lancamento_id integer,
  descricao text,
  valor_centavos integer,
  data text,
  criado_em text not null);
create table projeto_fato(
  id integer primary key,
  projeto_id integer not null references projeto(id),
  texto text not null,
  data_fato text,
  pessoa_nome text,
  anexo_id integer references anexo(id),
  atividade_id integer,
  registrado_em text not null,
  origem text not null);
