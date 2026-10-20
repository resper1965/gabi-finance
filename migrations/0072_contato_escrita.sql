-- 0072: escrita aprovada de contatos no Graph da ness (tarefa 1: só a leitura passa a guardar o que a escrita vai precisar).
-- contato_graph: um telefone de um contato da ness como veio do Graph (graph_id do contato, campo de origem e texto original);
-- `telefone` é o E.164 normalizado (nulo quando o texto não vira número válido, ex. ramal).
-- contato_proposta: correção/criação proposta, decidida pelo dono; nada é escrito no Graph sem estado 'aprovada'. Dado de terceiros: nunca em log.
create table contato_graph(
  conta text not null,
  graph_id text not null,
  nome text,
  telefone_original text not null,
  telefone text,
  campo text check (campo in ('mobile','home','business')),
  atualizado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  primary key (conta, graph_id, telefone_original));
create index contato_graph_telefone on contato_graph(telefone);

create table contato_proposta(
  id integer primary key,
  tipo text not null check (tipo in ('criar','corrigir')),
  conta text not null,
  graph_id text,
  nome_antes text,
  telefone_antes text,
  nome_depois text not null,
  telefone_depois text not null,
  origem text not null check (origem in ('whatsapp','telefone_invalido')),
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','recusada','aplicada','falhou')),
  motivo text,
  criada_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  decidida_em text,
  decidida_por text,
  aplicada_em text);
create unique index contato_proposta_aberta on contato_proposta(conta, tipo, coalesce(graph_id,''), telefone_depois)
  where estado in ('pendente','aprovada');
