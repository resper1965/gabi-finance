-- 0003_captura: campos que a captura do Open Finance grava além dos de 0002.
alter table lancamento add column natureza text check (natureza in ('caixa+custo','caixa','custo','neutro'));
alter table lancamento add column operacao text;
alter table conta add column titular text;
alter table conta add column limite_centavos integer;
alter table conta add column disponivel_centavos integer;
alter table conta add column vencimento_fatura text;
