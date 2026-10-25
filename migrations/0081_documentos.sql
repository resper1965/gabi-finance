-- 0081: documentos de qualquer tipo (spec 2026-10-23-documentos §1), de pessoa ou de bem (imóvel, veículo, outro).
-- Copia pessoa_documento para documento (+ número 'numero', + datas emissao/validade, mesmos ids) e pessoa_proposta para
-- documento_proposta (todas: as decididas guardam o que o Ricardo já recusou); as antigas ficam como *_legado, não lidas mais.
-- familia_documento e familia_proposta: as tabelas novas no formato da família (só leitura), para a família responder igual.
-- Desfazer (perde tudo o que foi aprovado, recusado ou lido depois da instalação; passos completos em docs/runbook.md#documentos):
--   com a API e o timer parados e backup do banco, numa transação:
--   drop view familia_proposta; drop view familia_documento; drop table documento_leitura; drop table documento_proposta;
--   drop table documento_data; drop table documento_numero; drop table documento; drop table bem;
--   alter table pessoa_documento_legado rename to pessoa_documento; alter table pessoa_proposta_legado rename to pessoa_proposta;
--   delete from schema_versao where nome='0081_documentos.sql';
--   e voltar o código para antes do merge (senão a API aplica a 0081 de novo ao subir).
create table bem(
  id text primary key,
  tipo text not null check (tipo in ('imovel','veiculo','outro')),
  nome text not null,
  dados text not null default '{}' check (json_valid(dados)),
  criado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  excluido_em text);
create table documento(
  id integer primary key,
  titular_tipo text not null check (titular_tipo in ('pessoa','bem')),
  titular_id text not null,
  tipo text not null,
  pais text not null default 'BR',
  emissor text,
  paperless_id integer,
  origem text not null check (origem in ('legado','ricardo','carga','leitura')),
  criado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  atualizado_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  excluido_em text);
create index documento_titular on documento(titular_tipo, titular_id);
-- O primeiro número (menor id) é o principal.
create table documento_numero(
  id integer primary key,
  documento_id integer not null references documento(id),
  nome text not null,
  valor text not null);
create index documento_numero_doc on documento_numero(documento_id);
create table documento_data(
  documento_id integer not null references documento(id),
  tipo text not null check (tipo in ('emissao','validade','vigencia_inicio','vigencia_fim','vencimento','renovacao')),
  data text not null,
  primary key (documento_id, tipo));
create index documento_data_data on documento_data(data);
create table documento_proposta(
  id integer primary key,
  doc text not null check (json_valid(doc)),
  documento_id integer references documento(id),
  bem_novo text check (bem_novo is null or json_valid(bem_novo)),
  paperless_id integer,
  conferir integer not null default 0 check (conferir in (0,1)),
  motivos text not null default '[]' check (json_valid(motivos)),
  estado text not null default 'pendente' check (estado in ('pendente','aprovada','recusada')),
  origem text not null check (origem in ('hermes','carga','leitura')),
  criada_em text not null default (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  decidida_em text,
  decidida_por text);
create index documento_proposta_estado on documento_proposta(estado);
create table documento_leitura(
  paperless_id integer primary key,
  modificado text,
  estado text not null check (estado in ('lido','sem_texto','sem_documento','falhou')),
  motivo text,
  custo real not null default 0,
  tentativas integer not null default 0,
  lido_em text not null);

insert into documento(id, titular_tipo, titular_id, tipo, pais, emissor, paperless_id, origem, criado_em, atualizado_em, excluido_em)
select id, 'pessoa', pessoa_id, tipo, pais, emissor, paperless_id, origem, criado_em, atualizado_em, excluido_em from pessoa_documento;
insert into documento_numero(documento_id, nome, valor) select id, 'numero', numero from pessoa_documento order by id;
insert into documento_data(documento_id, tipo, data) select id, 'emissao', emissao from pessoa_documento where emissao is not null;
insert into documento_data(documento_id, tipo, data) select id, 'validade', validade from pessoa_documento where validade is not null;
insert into documento_proposta(id, doc, documento_id, paperless_id, conferir, estado, origem, criada_em, decidida_em, decidida_por)
select id,
  json_object('titular_tipo','pessoa','titular_id',pessoa_id,'tipo',tipo,'pais',pais,'emissor',emissor,
    'numeros',json_array(json_object('nome','numero','valor',numero)),
    'datas',json(case
      when emissao is not null and validade is not null
        then json_array(json_object('tipo','emissao','data',emissao), json_object('tipo','validade','data',validade))
      when emissao is not null then json_array(json_object('tipo','emissao','data',emissao))
      when validade is not null then json_array(json_object('tipo','validade','data',validade))
      else '[]' end)),
  documento_id, paperless_id, conferir, estado, origem, criada_em, decidida_em, decidida_por
from pessoa_proposta order by id;
alter table pessoa_proposta rename to pessoa_proposta_legado;
alter table pessoa_documento rename to pessoa_documento_legado;

create view familia_documento as
select d.id, d.titular_id pessoa_id, d.tipo, d.pais,
  (select n.valor from documento_numero n where n.documento_id=d.id order by n.id limit 1) numero,
  d.emissor,
  (select x.data from documento_data x where x.documento_id=d.id and x.tipo='emissao') emissao,
  (select x.data from documento_data x where x.documento_id=d.id and x.tipo='validade') validade,
  d.paperless_id, d.origem, d.criado_em, d.atualizado_em, d.excluido_em
from documento d where d.titular_tipo='pessoa';
create view familia_proposta as
select p.id, json_extract(p.doc,'$.titular_id') pessoa_id, p.documento_id, json_extract(p.doc,'$.tipo') tipo,
  json_extract(p.doc,'$.pais') pais, json_extract(p.doc,'$.numeros[0].valor') numero, json_extract(p.doc,'$.emissor') emissor,
  (select json_extract(j.value,'$.data') from json_each(p.doc,'$.datas') j where json_extract(j.value,'$.tipo')='emissao') emissao,
  (select json_extract(j.value,'$.data') from json_each(p.doc,'$.datas') j where json_extract(j.value,'$.tipo')='validade') validade,
  p.paperless_id, p.origem, p.conferir, p.estado, p.criada_em, p.decidida_em, p.decidida_por
from documento_proposta p where json_extract(p.doc,'$.titular_tipo')='pessoa';
