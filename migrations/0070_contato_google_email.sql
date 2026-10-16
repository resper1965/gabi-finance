-- 0070: e-mail dos contatos do Google (e-mail M4). Decisão do Ricardo em 16/10: a leitura de contatos passa a pedir também `emailAddresses`
-- (mesmo escopo contacts.readonly); o dado fica só neste banco. Tabela filha: um contato pode ter vários e-mails. `telefone` é o E.164 do
-- contato ('' quando o contato não tem telefone válido). Dado de terceiros (R14): nunca em log nem em aviso; nada é enviado para esses endereços.
create table contato_google_email(
  conta text not null,
  email text not null,
  telefone text not null default '',
  nome text,
  primary key (conta, email, telefone));
create index contato_google_email_telefone on contato_google_email(telefone);
