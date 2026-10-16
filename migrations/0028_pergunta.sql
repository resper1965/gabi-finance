-- Canal de decisão (DC1): perguntas com opções numeradas, respondidas pelo Ricardo no Telegram/WhatsApp (via Hermes).
-- `opcoes` é JSON [{n, rotulo, efeito, parametros}]; `efeito` só vale se estiver na lista fechada de gabi/decisoes.py.
create table pergunta(
  id integer primary key autoincrement,
  tipo text not null,
  titulo text not null,
  contexto text,
  opcoes text not null,
  estado text not null default 'aberta' check (estado in ('aberta','respondida','expirada')),
  criada_em text not null,
  respondida_em text,
  escolha integer,
  origem text);
create index pergunta_estado on pergunta(estado, id);
