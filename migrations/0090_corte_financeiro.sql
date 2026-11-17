-- Corte do gabi-finance: remove as tabelas das áreas que saíram (agenda e e-mail sincronizados, Teams, contatos, envios, família/documentos/bens,
-- projetos, atividades, anexos). Só `drop`: nenhuma linha de `pessoa` (nem de qualquer tabela que fica) é tocada.
-- Ordem das chaves estrangeiras: filhas antes das mães (o banco roda com foreign_keys=ON). `if exists` deixa a migração idempotente em bancos parciais.
-- Ficam, mesmo sem módulo que as alimente, as que código que fica ainda lê ou grava: agenda_evento/agenda_fonte (dinheiro.sugestoes_agenda, envelope),
-- pet/allowlist_vip/memoria/agenda_estado/agenda_eventos/compromisso_fixo/conta_estado (importar, o carregador do staging) e custo_modelo (dinheiro.modelo).

-- visões da família
drop view if exists familia_documento;
drop view if exists familia_proposta;

-- projetos, anexos e atividades
drop table if exists projeto_fato;
drop table if exists projeto_gasto;
drop table if exists projeto_pessoa;
drop table if exists anexo;
drop table if exists atividade;
drop table if exists projeto;

-- documentos e bens da família
drop table if exists documento_data;
drop table if exists documento_numero;
drop table if exists documento_proposta;
drop table if exists documento_leitura;
drop table if exists documento;
drop table if exists pessoa_proposta_legado;
drop table if exists pessoa_documento_legado;
drop table if exists pessoa_historico;
drop table if exists bem;

-- e-mail
drop table if exists email_msg;
drop table if exists email_respondido;
drop table if exists email_fonte;
drop table if exists caixa_email;

-- contatos, envios, escuta e Teams
drop table if exists contato_google_email;
drop table if exists contato_google;
drop table if exists contato_graph;
drop table if exists contato_proposta;
drop table if exists envio_proposta;
drop table if exists escuta_remetente;
drop table if exists teams_conversa;
drop table if exists teams_fonte;
