-- 0023: escuta — falha temporária (Paperless, ponte, modelo sem resposta) tenta de novo com espera crescente em vez de virar `falhou`.
-- tentativas: falhas temporárias já ocorridas; proxima_em: instante (ISO, mesmo formato do `agora` da rodada) antes do qual a mensagem não é tentada.
alter table escuta_msg add column tentativas integer not null default 0;
alter table escuta_msg add column proxima_em text;
