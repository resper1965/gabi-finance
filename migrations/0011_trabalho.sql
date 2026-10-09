-- 0011: Fase 3 (Trabalho). Só cabeçalho e trecho do e-mail; corpo e anexo ficam na origem.
create table caixa_email(
  id integer primary key,
  endereco text not null unique,
  provedor text not null check (provedor in ('graph','google')),
  papel text,
  empresa_id text references empresa(id),
  como_entra text,
  le integer not null default 1,
  rascunho integer not null default 0,
  frente_padrao_id integer,
  migra_para text,
  ler_a_partir_de text,
  cursor text,
  estado text not null default 'a_decidir' check (estado in ('a_decidir','sim','nao'))
);
create table item_email(
  id integer primary key,
  caixa_id integer not null references caixa_email(id),
  message_id text not null unique,
  remetente text not null,
  assunto text,
  recebido_em text not null,
  trecho text,
  frente_id integer,
  relevante integer,
  motivo text,
  estado text not null default 'novo' check (estado in ('novo','descartado','apagado'))
);
create index item_email_recebido on item_email(recebido_em);
create table regra_expurgo(
  id integer primary key,
  remetente_contem text,
  assunto_contem text,
  ligada integer not null default 0,
  criada_em text not null
);
create table evento(
  id integer primary key,
  caixa_id integer not null references caixa_email(id),
  externo_id text not null,
  inicio text not null,
  fim text not null,
  titulo text,
  participantes text,
  link_reuniao text,
  unique(caixa_id, externo_id)
);
create table tarefa(
  id integer primary key,
  origem text not null,
  externo_id text not null,
  titulo text not null,
  prazo text,
  estado text not null default 'aberta' check (estado in ('aberta','concluida')),
  unique(origem, externo_id)
);
create table frente(
  id integer primary key,
  nome text not null,
  tipo text not null check (tipo in ('cliente','prospect','projeto','interno','pessoal')),
  empresa_id text references empresa(id),
  regra text,
  pai_id integer references frente(id)
);
create table item_frente(
  frente_id integer not null references frente(id),
  tipo text not null,
  ref_id integer not null,
  origem text not null,
  estado text not null check (estado in ('sugerido','confirmado')),
  primary key (frente_id, tipo, ref_id)
);
