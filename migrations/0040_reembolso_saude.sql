-- Reembolso de saúde (D8): SÓ referência, estado e contagens no gabi.db (ADR-014). Paciente, prestador, valor, CPF/CNPJ, conselho e especialidade
-- vivem no cofre cifrado (tabelas reembolso_doc e reembolso_dossie, criadas por gabi/reembolso_saude/cofre.py). Nenhuma coluna de saúde aqui.
create table reembolso_saude_doc(
  paperless_id integer primary key,
  estado text not null check (estado in ('novo','classificado','falhou')),
  tentativas integer not null default 0,
  motivo text,                       -- código fixo (ex.: 'sem texto legível'), nunca texto do documento
  atualizado_em text not null);
-- Projeção reconstruída a cada rodada a partir do cofre: o MCP (sem a chave do cofre) lê só isto. `id` é o número do dossiê, dado pelo cofre.
create table reembolso_saude_dossie(
  id integer primary key,
  mes text not null,                 -- AAAA-MM do atendimento
  estado text not null check (estado in ('a_pedir','sem_nf','sem_aprovacao','a_conferir','pedido','recebido')),
  docs integer not null,
  pronto integer not null default 0,
  faltam text not null default '[]', -- JSON com códigos fixos (nf, comprovante, conselho...)
  doc_ids text not null default '[]',-- JSON com os ids do Paperless
  parado_desde text,
  atualizado_em text not null);
-- Declarações do Ricardo ("pedi", "recebi") feitas pelo canal; o cofre só muda na rodada seguinte, que as aplica.
create table reembolso_saude_acao(
  id integer primary key autoincrement,
  dossie_id integer not null,
  acao text not null check (acao in ('pedi','recebi')),
  protocolo text,                    -- do plano; apagado depois de aplicado
  criado_em text not null,
  aplicado_em text,
  resultado text);                   -- aplicado | sem_documentos | dossie_inexistente
create index reembolso_saude_acao_aberta on reembolso_saude_acao(aplicado_em);
