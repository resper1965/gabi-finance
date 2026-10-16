-- Exames em PDF: só a referência do documento do Paperless e o estado da extração. NENHUM valor, marcador ou paciente aqui (ADR-014): isso vive no cofre cifrado.
create table exame_doc(
  paperless_id integer primary key,
  estado text not null check (estado in ('novo','extraido','confirmado','falhou')),
  versao integer not null default 0,
  motivo text,
  atualizado_em text not null);
