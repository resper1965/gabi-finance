-- 0015: concluir tarefa na origem sem rede na API. A API só registra o pedido; o job do Trabalho (único com rede) conclui no Graph/Google.
alter table tarefa add column pedido_concluir_em text;
