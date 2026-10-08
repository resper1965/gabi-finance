-- 0002_dinheiro: contas, lançamentos, regras/sugestões, conferências. Dinheiro em centavos (R7); origem por campo (R9).
create table conta(
  id integer primary key, externo_id text not null unique, instituicao text, tipo text, apelido text,
  pj integer not null default 0,
  estado text not null default 'a_decidir' check (estado in ('a_decidir','sim','nao')),
  nibo_account_id text, excluido_em text);

create table categoria(id integer primary key, nome text not null unique, pai_id integer references categoria(id));
create table equivalencia_categoria(
  origem_pluggy text not null unique, categoria_id integer not null references categoria(id));

create table lancamento(
  id integer primary key,
  conta_id integer not null references conta(id),
  externo_id text not null unique,
  data text not null,
  valor_centavos integer not null,
  descricao_original text,
  estabelecimento text,
  forma text,
  categoria_id integer references categoria(id),
  categoria_origem text check (categoria_origem in ('banco','regra','gabi','voce','fonte')),
  para_quem_id text references pessoa(id),
  para_quem_origem text check (para_quem_origem in ('banco','regra','gabi','voce','fonte')),
  empresa_id text references empresa(id),
  empresa_origem text check (empresa_origem in ('banco','regra','gabi','voce','fonte')),
  frente_id integer,
  fatura_id text,
  parcela integer, parcelas integer, data_compra text,
  status text not null default 'posted' check (status in ('pending','posted')),
  bruto_ref text);
create index lancamento_conta_data on lancamento(conta_id, data);
create index lancamento_estabelecimento on lancamento(estabelecimento);

-- A fatura já existe (0001): ganha o status de pagamento da Pluggy e o vínculo com a conta.
alter table fatura add column pagamento_status text;
alter table fatura add column conta_id integer references conta(id);

create table regra(
  id integer primary key, padrao text not null, acao text not null,
  ativa integer not null default 0,  -- R1: nasce inativa; só vale depois do Ricardo ligar
  criado_em text not null, criada_por text);

create table sugestao(
  id integer primary key,
  tipo text not null check (tipo in ('categoria','para_quem','empresa','regra','tarefa')),
  lancamento_id integer references lancamento(id),
  payload text not null,
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','rejeitada')),
  motivo text, criado_em text not null, decidida_em text);

create table saldo(
  conta_id integer not null references conta(id), em text not null, saldo_centavos integer not null,
  primary key (conta_id, em));

create table conferencia(
  id integer primary key,
  rodada_id integer not null references rodada(id),
  tipo text not null check (tipo in ('saldo_final','dias_sem_buraco','volume_proximo')),
  conta_id integer references conta(id), ok integer not null, detalhe text, criado_em text);

create table assinatura(
  id integer primary key, estabelecimento text not null unique,
  status text not null default 'a_conferir' check (status in ('a_conferir','manter','cancelar','nao_assinatura','encerrada')),
  lembrar_ate_cancelar integer not null default 0);
