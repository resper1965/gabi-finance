-- "Reembolso por" da assinatura: a empresa que reembolsa as cobranças dela (vazio = pessoal).
-- assinatura_reembolso guarda os lançamentos que a própria assinatura marcou, para poder desfazer só esses.
alter table assinatura add column empresa_id text references empresa(id);
create table assinatura_reembolso(
  lancamento_id integer primary key references lancamento(id),
  assinatura_id integer not null references assinatura(id),
  empresa_id text not null);
