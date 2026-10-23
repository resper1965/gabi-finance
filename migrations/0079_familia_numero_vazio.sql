-- 0079: a 0077 copiou do cadastro antigo documentos cujo número era o texto "null"/"None" (campo nunca preenchido); o Hermes os lia
-- como "cadastrado, número em branco". Sai do cadastro com excluido_em (o dado antigo segue em pessoa.dados.documentos).
-- Desfazer: update pessoa_documento set excluido_em=null where origem='legado' and lower(trim(numero)) in ('null','none','nil','-','n/a');
update pessoa_documento set excluido_em=strftime('%Y-%m-%dT%H:%M:%SZ','now')
where origem='legado' and excluido_em is null and lower(trim(numero)) in ('null','none','nil','-','n/a');
