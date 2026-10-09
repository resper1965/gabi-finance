-- 0014: crédito no extrato casado com uma NFS-e. O app PROPÕE com confiança e motivo; só o Ricardo confirma (R1).
-- Nibo defasado: o recebimento real é o crédito na conta PJ, nunca o `nibo_pago` da nota.
create table recebimento_nota(
  id integer primary key,
  nota_id text not null references nota_fiscal(id),
  lancamento_id integer not null references lancamento(id),
  confianca real not null,
  motivo text not null,
  estado text not null default 'proposto' check (estado in ('proposto','confirmado','rejeitado')),
  criado_em text not null,
  unique(nota_id, lancamento_id));
create index recebimento_nota_estado on recebimento_nota(estado);
