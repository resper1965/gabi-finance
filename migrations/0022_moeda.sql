-- 0022: moeda estrangeira. valor_centavos passa a ser SEMPRE em reais (amountInAccountCurrency do mcp.ai); nunca se estima câmbio.
-- moeda: NULL = BRL. valor_original_centavos: valor na moeda da compra (mesmo sinal de valor_centavos); NULL em BRL.
-- convertido: 0 = estrangeiro sem valor em reais; valor_centavos guarda o original e um aviso é gerado.
alter table lancamento add column moeda text;
alter table lancamento add column valor_original_centavos integer;
alter table lancamento add column convertido integer not null default 1;
