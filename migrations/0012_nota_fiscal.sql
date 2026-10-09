-- 0012: histórico das NFS-e emitidas (fonte: Nibo, só leitura). Previsão de caixa: vencimento + valor líquido; recebimento real vem do extrato.
create table nota_fiscal(
  id text primary key,                 -- id da nota no Nibo
  numero text,
  rps_numero text,
  rps_serie text,
  codigo_verificacao text,
  emitente_cnpj text,                  -- NULL em parte das notas do Nibo (informado como veio)
  emissao text,                        -- AAAA-MM-DD (autorização; se faltar, criação)
  status text not null check (status in ('autorizada','cancelada','negada')),
  valor_bruto_centavos integer not null,
  deducoes_centavos integer not null default 0,
  descontos_centavos integer not null default 0,
  tomador_nome text,
  tomador_doc text,
  tomador_email text,
  descricao text,
  retencoes text not null default '{}',   -- JSON: iss, ir, pis, cofins, csll, inss como vieram
  agendamento_id text,                 -- schedule (a receber) do Nibo
  vencimento text,                     -- AAAA-MM-DD
  valor_liquido_centavos integer,      -- valor do agendamento (depois das retenções)
  nibo_pago integer not null default 0,         -- o que o Nibo diz; NÃO é prova de recebimento (Nibo defasado)
  nibo_pago_centavos integer not null default 0,
  pdf_id text, xml_id text,
  pdf_arquivo text, xml_arquivo text,  -- caminho relativo à pasta de notas
  nibo_atualizado_em text,
  importado_em text not null,
  atualizado_em text not null
);
create index nota_fiscal_vencimento on nota_fiscal(vencimento);
create index nota_fiscal_tomador on nota_fiscal(tomador_doc);
