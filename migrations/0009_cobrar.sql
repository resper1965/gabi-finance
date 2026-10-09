-- 0009: Fase 2 (Cobrar) — comprovantes do Paperless e vínculo proposto/confirmado com lançamentos (R1: a Gabi propõe, o Ricardo confirma).
create table comprovante(
  id integer primary key,
  paperless_id integer not null unique,
  tipo text not null,
  valor_centavos integer not null,
  data text not null,
  cnpj text,
  pessoa_id text references pessoa(id));

create table comprovante_vinculo(
  id integer primary key,
  comprovante_id integer not null references comprovante(id),
  lancamento_id integer not null references lancamento(id),
  confianca real not null check (confianca >= 0 and confianca <= 1),
  motivo text not null,
  estado text not null default 'proposto' check (estado in ('proposto','confirmado','rejeitado')),
  criado_em text not null, decidido_em text, decidido_por text,
  unique (comprovante_id, lancamento_id));
create index comprovante_vinculo_lancamento on comprovante_vinculo(lancamento_id, estado);

-- Reembolsos de contratantes (ness, IONIC): a Bekaa (pj_titular) nunca entra aqui, vai ao lote do Nibo (T2.4). Relação é cadastro (R6).
alter table empresa add column relacao text check (relacao is null or relacao in ('pj_titular','contratante'));

create table reembolso(
  id integer primary key,
  empresa_id text not null references empresa(id),
  estado text not null default 'a_cobrar' check (estado in ('a_cobrar','cobrado','parcialmente_recebido','quitado')),
  criado_em text not null, cobrado_em text);
create table reembolso_item(
  reembolso_id integer not null references reembolso(id),
  lancamento_id integer not null unique references lancamento(id),
  valor_centavos integer not null check (valor_centavos > 0),
  recebido_centavos integer not null default 0 check (recebido_centavos >= 0 and recebido_centavos <= valor_centavos),
  primary key (reembolso_id, lancamento_id));
create table reembolso_baixa(  -- um crédito baixa uma vez só
  credito_lancamento_id integer primary key references lancamento(id),
  empresa_id text not null references empresa(id), valor_centavos integer not null, criado_em text not null);

-- Lote diário "Lançar na PJ" (única gravação externa; Nibo da Bekaa). Despesa da Bekaa paga no PF vira agendamento a pagar ao sócio.
alter table categoria add column nibo_category_id text;  -- categoria equivalente no Nibo (cadastro; sem ela o item vira erro, nunca adivinha)
create table lote_nibo(
  id integer primary key,
  dia text not null,
  estado text not null default 'montado' check (estado in ('montado','confirmado','executado')),
  texto_confirmacao text not null, criado_em text not null);
create table lote_nibo_item(
  lote_id integer not null references lote_nibo(id),
  lancamento_id integer not null references lancamento(id),
  estado text not null default 'pendente' check (estado in ('pendente','ok','erro')),
  schedule_id text, erro text, baixa_credito_id integer references lancamento(id),
  primary key (lote_id, lancamento_id));
create index lote_nibo_item_lancamento on lote_nibo_item(lancamento_id, estado);

-- E-mail de cobrança: só RASCUNHO (ADR-006). O envio fica desabilitado; o app guarda e mostra.
create table cobranca(
  id integer primary key,
  empresa_id text not null references empresa(id),
  para text not null, assunto text not null, corpo text not null,
  criado_em text not null);
create table cobranca_item(
  cobranca_id integer not null references cobranca(id),
  lancamento_id integer not null references lancamento(id),
  primary key (cobranca_id, lancamento_id));
