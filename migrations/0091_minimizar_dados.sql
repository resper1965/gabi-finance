-- Minimização de dados do gabi-finance: derruba as três tabelas que só o carregador do staging gravava e que não são financeiras
-- (pets, lista de números autorizados do WhatsApp e memória de conversas). Nenhum módulo que fica as lê; `gabi.importar` deixou de gravá-las.
-- Só `drop`: `pessoa`, o dinheiro e o resto do que fica não são tocados. `if exists` deixa a migração idempotente.
drop table if exists pet;
drop table if exists allowlist_vip;
drop table if exists memoria;
