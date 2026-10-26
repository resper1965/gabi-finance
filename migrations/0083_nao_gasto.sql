-- 0083: o que não é gasto (26/10). Pagamento de fatura por boleto, Pix para empresa própria (Bekaa) e investimento saem de Gastos (natureza
-- 'caixa' em vez de 'caixa+custo'); a marcação manual do Ricardo (natureza_manual) vence qualquer regra. natureza_regra guarda o porquê.
-- Desfazer: alter table lancamento drop column natureza_regra; alter table lancamento drop column natureza_manual;
--           delete from schema_versao where nome='0083_nao_gasto.sql'; e rodar a captura (natureza volta à do caixa.natureza).
alter table lancamento add column natureza_manual text check (natureza_manual in ('gasto','nao_gasto'));
alter table lancamento add column natureza_regra text;
