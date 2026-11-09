-- 0089: projeto ligado ao Linear (09/11): o projeto e as etapas moram no Linear; o brain guarda a pasta (dinheiro, fatos, anexos, pessoas) ligada por linear_id.
-- Spec: docs/superpowers/specs/2026-11-09-projetos-no-linear-design.md (ADR-038). Só acrescenta colunas; nenhum dado migrado.
-- Desfazer: drop index projeto_linear_id; alter table projeto drop column linear_url; alter table projeto drop column linear_id;
--   delete from schema_versao where nome='0089_projeto_linear.sql';
alter table projeto add column linear_id text;
alter table projeto add column linear_url text;
create unique index projeto_linear_id on projeto(linear_id) where linear_id is not null;
