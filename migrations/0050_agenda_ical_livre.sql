-- 0050: agenda. `ical_uid` (iCalUID do Google) identifica o MESMO compromisso em contas diferentes mesmo com título diferente (dedupe; o título
-- continua como reserva quando não há uid). `livre` = transparency=transparent no Google ("disponível"): aparece na agenda, mas não conflita.
alter table agenda_evento add column ical_uid text;
alter table agenda_evento add column livre integer not null default 0 check (livre in (0,1));
