-- 0082: a receber manual (spec 2026-10-25-hermes-completo, Onda 3): valor que o Ricardo diz no chat que vai receber, fora das notas.
-- receber_manual_proposta casa o a receber com um crédito do extrato (mesma forma e estados de recebimento_nota; tabela própria
-- porque recebimento_nota.nota_id é not null). Valor negativo = desconto/adiantamento; não gera proposta.
-- Desfazer: drop table receber_manual_proposta; drop table receber_manual; delete from schema_versao where nome='0082_receber_manual.sql';
create table receber_manual(
  id integer primary key,
  pagador text not null check (length(trim(pagador)) > 0),
  valor_centavos integer not null check (valor_centavos <> 0),
  vencimento text,
  conta text,
  observacao text,
  estado text not null default 'aberto' check (estado in ('aberto','recebido','cancelado')),
  lancamento_id integer references lancamento(id),
  criado_em text not null,
  quem text not null,
  atualizado_em text not null);
create table receber_manual_proposta(
  id integer primary key,
  receber_id integer not null references receber_manual(id),
  lancamento_id integer not null references lancamento(id),
  confianca real not null,
  motivo text not null,
  estado text not null default 'proposto' check (estado in ('proposto','confirmado','rejeitado')),
  criado_em text not null,
  unique(receber_id, lancamento_id));
create index receber_manual_estado on receber_manual(estado);
create index receber_manual_proposta_estado on receber_manual_proposta(estado);
