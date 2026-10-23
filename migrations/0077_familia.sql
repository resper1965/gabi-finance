-- 0077: cadastro familiar (spec 2026-10-22-cadastro-familiar): documentos, histórico de contato e propostas de documento.
-- Copia pessoa.dados.documentos (tipo, numero, emissor) para pessoa_documento com origem 'legado'; dados.documentos fica intacto (dado nunca se perde).
-- Desfazer: drop table pessoa_proposta; drop table pessoa_historico; drop table pessoa_documento.
create table pessoa_documento(
  id integer primary key,
  pessoa_id text not null references pessoa(id),
  tipo text not null check (tipo in ('cpf','rg','cnh','passaporte','outro')),
  pais text not null default 'BR',
  numero text not null,
  emissor text,
  emissao text,
  validade text,
  paperless_id integer,
  origem text not null check (origem in ('legado','ricardo','carga')),
  criado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  atualizado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  excluido_em text);
create index pessoa_documento_pessoa on pessoa_documento(pessoa_id);
create index pessoa_documento_validade on pessoa_documento(validade);
create table pessoa_historico(
  id integer primary key,
  pessoa_id text not null references pessoa(id),
  campo text not null,
  antes text,
  depois text,
  quem text not null,
  quando text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  desfeito_em text);
create index pessoa_historico_pessoa on pessoa_historico(pessoa_id);
create table pessoa_proposta(
  id integer primary key,
  pessoa_id text not null references pessoa(id),
  documento_id integer references pessoa_documento(id),
  tipo text not null check (tipo in ('cpf','rg','cnh','passaporte','outro')),
  pais text not null default 'BR',
  numero text not null,
  emissor text,
  emissao text,
  validade text,
  paperless_id integer,
  origem text not null check (origem in ('hermes','carga')),
  conferir integer not null default 0 check (conferir in (0,1)),
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','recusada')),
  criada_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  decidida_em text,
  decidida_por text);
create unique index pessoa_proposta_aberta on pessoa_proposta(pessoa_id, tipo, numero) where estado='pendente';
insert into pessoa_documento(pessoa_id, tipo, numero, emissor, origem)
select p.id,
  case replace(replace(replace(replace(replace(replace(replace(replace(lower(trim(coalesce(json_extract(d.value,'$.tipo'),''))),
        'ã','a'),'á','a'),'â','a'),'ç','c'),'é','e'),'í','i'),'ó','o'),'ú','u')
    when 'cpf' then 'cpf'
    when 'rg' then 'rg' when 'identidade' then 'rg' when 'carteira de identidade' then 'rg'
    when 'cnh' then 'cnh' when 'carteira de motorista' then 'cnh' when 'carteira nacional de habilitacao' then 'cnh' when 'habilitacao' then 'cnh'
    when 'passaporte' then 'passaporte'
    else 'outro' end,
  trim(cast(json_extract(d.value,'$.numero') as text)),
  nullif(trim(cast(json_extract(d.value,'$.emissor') as text)),''),
  'legado'
from pessoa p, json_each(case when json_valid(p.dados) and json_type(p.dados,'$.documentos')='array' then p.dados else '{"documentos":[]}' end, '$.documentos') d
where p.excluido_em is null
  and json_type(d.value)='object'
  and length(trim(coalesce(cast(json_extract(d.value,'$.numero') as text),''))) between 1 and 40;
