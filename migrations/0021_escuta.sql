-- 0021: escuta do WhatsApp (substitui o agente do OpenClaw) — mensagens recebidas, remetentes/grupos autorizados e contatos do Google.
create table escuta_msg(
  id integer primary key,
  id_externo text not null unique,
  de text not null,
  grupo integer not null default 0,
  id_grupo text,
  recebida_em text not null,
  texto text,
  anexo_caminho text,
  estado text not null default 'nova' check (estado in ('nova','processada','retida','falhou')),
  tipo text,
  confianca real,
  campos text,
  processada_em text);
create index escuta_msg_estado on escuta_msg(estado, recebida_em);

create table escuta_remetente(
  numero text primary key,
  nome text,
  estado text not null check (estado in ('pendente','aprovado','ignorado','bloqueado')),
  vista_em text,
  qtd integer not null default 0);

create table escuta_grupo(
  id_grupo text primary key,
  nome text,
  aprovado integer not null default 0);

create table contato_google(
  conta text not null,
  telefone text not null,
  nome text,
  primary key (conta, telefone));
