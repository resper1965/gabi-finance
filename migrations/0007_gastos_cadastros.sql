-- 0007: assinatura lembra desde quando foi marcada; cadastros ganham exclusão lógica (R10); custo do modelo (OpenRouter).
alter table assinatura add column status_em text;
alter table pessoa add column excluido_em text;
alter table empresa add column excluido_em text;
alter table categoria add column excluido_em text;
create table custo_modelo(id integer primary key, em text not null, custo_usd real not null, tarefa text);
