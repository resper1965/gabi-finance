-- 0051: e-mail. `dispensada_em` = o dono marcou a mensagem (importante/emergencial/normal) como tratada: sai das listas e do resumo da manhã
-- sem ir à lixeira e sem mexer na caixa do Gmail. Desfazer zera a coluna. Independe de `estado` (a mensagem segue classificada/alertada).
alter table email_msg add column dispensada_em text;
