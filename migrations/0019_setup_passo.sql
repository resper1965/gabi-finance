-- 0019: progresso do assistente de configuração. Guarda SÓ o estado do passo e um detalhe em português; nunca credencial (R5).
create table setup_passo(
  passo text primary key,
  estado text not null check (estado in ('feito','depois')),
  detalhe text,
  atualizado_em text not null
);
