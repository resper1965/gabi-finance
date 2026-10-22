-- ADR-023 (simplificação de 21/10/2026): saem SÓ as tabelas que estavam vazias no banco de produção (conferido antes do deploy).
-- Legadas com dado ficam, sem código que as use: escuta_remetente, caixa_email, memoria. Filhas antes das mães (chave estrangeira).
drop table if exists escuta_msg;
drop table if exists escuta_grupo;
drop table if exists exame_doc;
drop table if exists reembolso_saude_acao;
drop table if exists reembolso_saude_doc;
drop table if exists reembolso_saude_dossie;
drop table if exists edicao_externa;
drop table if exists liberacao_sensivel;
drop table if exists item_frente;
drop table if exists item_email;
drop table if exists frente;
drop table if exists evento;
drop table if exists tarefa;
drop table if exists entrega;
drop table if exists regra_expurgo;
drop table if exists cobranca_item;
drop table if exists cobranca;
drop table if exists comprovante_vinculo;
drop table if exists comprovante;
drop table if exists reembolso_baixa;
drop table if exists reembolso_item;
drop table if exists reembolso;
drop table if exists lote_nibo_item;
drop table if exists lote_nibo;
drop table if exists pedido;
drop table if exists setup_passo;
-- Índice de busca da memória: nenhum código o consulta; a tabela memoria fica.
drop trigger if exists memoria_ai;
drop trigger if exists memoria_ad;
drop trigger if exists memoria_au;
drop table if exists memoria_fts;
