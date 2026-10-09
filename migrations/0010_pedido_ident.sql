-- 0010: o pedido guarda QUEM enviou (identificador exato no canal), para o aviso de volta ir ao remetente certo.
alter table pedido add column solicitante_ident text;

-- As colunas de 0009 que duplicavam o JSON `dados` do cadastro (relação da empresa, canais e permissão de pedido) saem: Cadastros já edita `dados`.
alter table empresa drop column relacao;
alter table pessoa drop column canais;
alter table pessoa drop column pode_pedir;
