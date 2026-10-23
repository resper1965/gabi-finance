-- 0078: a proposta aberta é única por pessoa, tipo, PAÍS e número (passaporte BR e PT com o mesmo número são documentos diferentes).
-- Desfazer: drop index pessoa_proposta_aberta; create unique index pessoa_proposta_aberta on pessoa_proposta(pessoa_id, tipo, numero) where estado='pendente';
drop index pessoa_proposta_aberta;
create unique index pessoa_proposta_aberta on pessoa_proposta(pessoa_id, tipo, pais, numero) where estado='pendente';
