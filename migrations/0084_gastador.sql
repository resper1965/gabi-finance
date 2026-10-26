-- 0084: quem gastou (26/10), separado de "para quem". Gastador = portador da conta (conta.usuarios). Cartão de um portador e conta corrente
-- preenchem sozinhos (origem 'cartao'); nos compartilhados o Ricardo indica ('voce') ou fica a indicar. gastador_regra = "sempre assim"
-- por loja NAQUELE cartão (origem 'regra'). Spec: docs/superpowers/specs/2026-10-26-gastadores-design.md.
-- Desfazer: drop table gastador_regra; alter table lancamento drop column gastador_origem; alter table lancamento drop column gastador_id;
--           delete from schema_versao where nome='0084_gastador.sql';
alter table lancamento add column gastador_id text references pessoa(id);
alter table lancamento add column gastador_origem text check (gastador_origem in ('cartao','voce','regra'));
create table gastador_regra(
  id integer primary key,
  conta_id integer not null references conta(id),
  estabelecimento text not null,
  pessoa_id text not null references pessoa(id),
  criado_em text not null,
  unique(conta_id, estabelecimento));
create index lancamento_gastador on lancamento(gastador_id);
