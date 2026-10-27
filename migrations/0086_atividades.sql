-- 0086: atividades (27/10): to-do pessoal que o Hermes cria a partir de um recado; avisos pelo produtor de `aviso`.
-- Spec: docs/superpowers/specs/2026-10-27-atividades-design.md. vence_em em UTC (ISO); tem_hora=0 = dia todo (00:00 de Brasília).
-- Desfazer: drop table atividade; delete from schema_versao where nome='0086_atividades.sql';
create table atividade(
  id integer primary key,
  texto text not null,
  vence_em text,
  tem_hora integer not null default 0,
  status text not null default 'aberta' check (status in ('aberta','feita','cancelada')),
  origem text not null,
  criada_em text not null,
  concluida_em text);
create index atividade_status_vence on atividade(status, vence_em);
