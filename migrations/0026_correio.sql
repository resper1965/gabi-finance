-- 0026: correio (e-mail do Google: ler, priorizar, lixeira, alertar), fonte própria separada de `caixa_email` (spec 2026-10-11-email-design).
-- A 0024 fica reservada aos exames e a 0025 é da agenda. Não guarda corpo completo, destinatários nem anexos: só o necessário para priorizar.
-- `trecho` é curto e apagado depois de `email.retencao_dias`. Leitura (`estado`) e lixeira (`lixeira`) são chaves separadas por conta.
create table email_fonte(
  id integer primary key,
  conta text not null unique,
  provedor text not null check (provedor in ('google','graph')),
  estado text not null default 'a_decidir' check (estado in ('a_decidir','sim','nao')),
  lixeira integer not null default 0 check (lixeira in (0,1)),
  history_id text,
  sincronizada_em text,
  recarga_em text,
  ultimo_erro text);

create table email_msg(
  id integer primary key,
  fonte_id integer not null references email_fonte(id),
  externo_id text not null,
  thread_id text,
  remetente text,
  assunto text,
  recebida_em text not null,
  trecho text,
  lista integer not null default 0 check (lista in (0,1)),
  classe text check (classe in ('normal','importante','emergencial','lixo')),
  prioridade integer check (prioridade between 0 and 3),
  motivo text,
  confianca real,
  estado text not null default 'nova' check (estado in ('nova','classificada','alertada','na_lixeira','restaurada','falhou')),
  tentativas integer not null default 0,
  proxima_em text,
  atualizado_em text,
  unique(fonte_id, externo_id));
create index email_msg_estado on email_msg(estado);
create index email_msg_thread on email_msg(thread_id);
create index email_msg_recebida on email_msg(recebida_em);

-- Quem o dono já respondeu (To/Cc dos enviados): esse remetente nunca vai para a lixeira.
create table email_respondido(
  fonte_id integer not null references email_fonte(id),
  endereco text not null,
  em text not null,
  primary key(fonte_id, endereco));
