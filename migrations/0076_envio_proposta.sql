-- 0076: fila de propostas de envio (evento de agenda, mensagem do Teams) que só saem depois do "Enviar" do dono no painel (spec 2026-10-22-envios-anuencia).
-- `conteudo` é o JSON canônico do que sai e não muda depois de criado; `hash` = sha256 dele; `chave` = id do evento no Google / transactionId no Graph. Desfazer: drop table envio_proposta.
create table envio_proposta(
  id integer primary key,
  tipo text not null check (tipo in ('evento','teams_chat','teams_canal')),
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
create index envio_proposta_estado on envio_proposta(estado);
