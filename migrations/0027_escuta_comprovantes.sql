-- CP1 opção B: um grupo de WhatsApp pode ser a "caixa de comprovantes". Só o que o Ricardo encaminha para ele vai ao Paperless.
alter table escuta_grupo add column comprovantes integer not null default 0 check (comprovantes in (0, 1));
create unique index escuta_grupo_comprovantes_unico on escuta_grupo(comprovantes) where comprovantes = 1;
