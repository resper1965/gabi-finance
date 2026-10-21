-- 0074: proposta de e-mail para contato existente (tipo adicionar_email, coluna email_depois, origem google_email). SQLite não altera `check`: recria a
-- tabela preservando as linhas e o índice das propostas abertas. Desfazer: só com as linhas do tipo novo removidas antes.
create table contato_proposta_nova(
  id integer primary key,
  tipo text not null check (tipo in ('criar','corrigir','corrigir_nome','apagar_telefone','apagar_contato','adicionar_email')),
  conta text not null,
  graph_id text,
  nome_antes text,
  telefone_antes text,
  nome_depois text not null,
  telefone_depois text not null,
  email_depois text,
  origem text not null check (origem in ('whatsapp','telefone_invalido','nome_sujo','nome_curto','google_email')),
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','recusada','aplicada','falhou')),
  motivo text,
  criada_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  decidida_em text,
  decidida_por text,
  aplicada_em text);
insert into contato_proposta_nova(id, tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, estado, motivo, criada_em, decidida_em, decidida_por, aplicada_em)
  select id, tipo, conta, graph_id, nome_antes, telefone_antes, nome_depois, telefone_depois, origem, estado, motivo, criada_em, decidida_em, decidida_por, aplicada_em from contato_proposta;
drop table contato_proposta;
alter table contato_proposta_nova rename to contato_proposta;
create unique index contato_proposta_aberta on contato_proposta(conta, tipo, coalesce(graph_id,''), telefone_depois)
  where estado in ('pendente','aprovada');
