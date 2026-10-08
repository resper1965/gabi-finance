-- 0001_base: família, financeiro importado, memória (FTS5), auditoria. Dinheiro sempre em centavos (R7).
create table pessoa(id text primary key, nome text not null, papel text, telefone text, dados text, origem text);
create table pet(id text primary key, nome text not null, especie text, dados text, origem text);
create table empresa(id text primary key, nome text not null, cnpj text, dados text, origem text);
create table compromisso_fixo(
  id text primary key, descricao text not null, pessoa_id text, valor_texto text, periodicidade text,
  dia_vencimento integer, vigencia_ate text, dados text, origem text);
create table matriz_acesso(informacao text primary key, boss text, familia_vip text, terceiros text);
create table allowlist_vip(chave text primary key, pessoa text, rotulo text, telefone text);
create table acesso(
  login text primary key, pessoa_id text,
  nivel text not null check (nivel in ('boss','familia_vip','terceiros')), criado_em text not null);

create table compromisso(
  id integer primary key, origem text, linha_id text, nome text, vencimento text, vencimento_util text,
  valor_centavos integer, valor_fonte text, forma text, account_id text, estado text, motivo text,
  dados text, atualizado_em text);
create table fatura(
  id text primary key, account_id text, vencimento text, total_centavos integer, minimo_centavos integer);
create table conciliacao(
  tx_id text not null, compromisso_id integer not null, metodo text, diferenca_centavos integer, criado_em text,
  primary key (tx_id, compromisso_id));
create table conta_estado(
  account_id text primary key, banco text, nome text, tipo text, pj integer, ult_tx_real text,
  ult_sync_ok text, status_conexao text, saldo_centavos integer, atualizado_em text);
create table agenda_estado(
  chave text primary key, item text, emissor text, vencimento text, valor_centavos integer, status text, visto_em text);
create table agenda_eventos(
  chave text primary key, em text, item text, emissor text, vencimento text, valor_centavos integer,
  evento text, detalhe text);

create table memoria(
  id integer primary key, chave text not null unique, tipo text not null, path text, sessao text,
  papel text, timestamp real, texto text not null, origem text);
create virtual table memoria_fts using fts5(
  texto, content='memoria', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
create trigger memoria_ai after insert on memoria begin
  insert into memoria_fts(rowid, texto) values (new.id, new.texto);
end;
create trigger memoria_ad after delete on memoria begin
  insert into memoria_fts(memoria_fts, rowid, texto) values ('delete', old.id, old.texto);
end;
create trigger memoria_au after update on memoria begin
  insert into memoria_fts(memoria_fts, rowid, texto) values ('delete', old.id, old.texto);
  insert into memoria_fts(rowid, texto) values (new.id, new.texto);
end;

create table rodada(
  id integer primary key autoincrement, fonte text not null, inicio text not null, fim text,
  status text not null check (status in ('rodando','ok','erro')),
  lidos integer default 0, novos integer default 0, alterados integer default 0, erro text);
create table chamada(
  id integer primary key autoincrement, quando text not null, login text, metodo text not null,
  caminho text not null, status integer not null);
create table decisao(
  id integer primary key autoincrement, quando text not null, quem text not null, o_que text not null, origem text);
create table token_agente(
  id integer primary key autoincrement, nome text not null, escopo text not null, hash text not null unique,
  criado_em text not null, revogado_em text);
