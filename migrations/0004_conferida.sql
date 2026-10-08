-- 0004_conferida: uma rodada só "vale" (dados_ate) depois de passar nas conferências.
alter table rodada add column conferida integer not null default 0;
