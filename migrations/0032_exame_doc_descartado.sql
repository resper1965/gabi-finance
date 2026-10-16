-- Laudo rejeitado pelo dono passa a ter o estado 'descartado' em exame_doc (o CHECK da 0031 não o previa). SQLite não altera CHECK: recria a tabela.
create table exame_doc_nova(
  paperless_id integer primary key,
  estado text not null check (estado in ('novo','extraido','confirmado','falhou','descartado')),
  versao integer not null default 0,
  motivo text,
  atualizado_em text not null);
insert into exame_doc_nova select paperless_id, estado, versao, motivo, atualizado_em from exame_doc;
drop table exame_doc;
alter table exame_doc_nova rename to exame_doc;
