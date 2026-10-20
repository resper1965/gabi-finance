-- 0071: Teams (ness). Sem texto de mensagem: só metadados de conversa e horários (o conteúdo nunca é gravado).
-- `teams_fonte.estado` = o dono decide por conta (sim/nao/a_decidir). Desfazer: drop table teams_conversa; drop table teams_fonte.
create table teams_fonte (
  id integer primary key,
  conta text not null unique,
  estado text not null default 'a_decidir' check (estado in ('sim','nao','a_decidir')),
  coletada_em text,
  ultimo_erro text
);
create table teams_conversa (
  conta text not null,
  chat_id text not null,
  tipo text not null check (tipo in ('um_a_um','grupo')),
  de_nome text,
  ultima_para_mim_em text,
  minha_ultima_resposta_em text,
  ultimo_aviso_em text,
  cursor text,
  primary key (conta, chat_id)
);
