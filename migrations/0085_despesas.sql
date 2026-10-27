-- Despesas (CRUD): tipo da linha (fixa recorrente | avulsa) e mês dispensado em valor_do_mes.
alter table compromisso_linha add column tipo text not null default 'fixa' check (tipo in ('fixa','avulsa'));

create table valor_do_mes_nova(
  id integer primary key,
  mes text not null,                      -- AAAA-MM
  compromisso text not null references compromisso_linha(id),
  tipo text not null check (tipo in ('valor','pago','dispensado')),
  valor_centavos integer, vencimento text, data_pagamento text, origem text,
  linha_planilha integer);
insert into valor_do_mes_nova(id, mes, compromisso, tipo, valor_centavos, vencimento, data_pagamento, origem, linha_planilha)
  select id, mes, compromisso, tipo, valor_centavos, vencimento, data_pagamento, origem, linha_planilha from valor_do_mes;
drop table valor_do_mes;
alter table valor_do_mes_nova rename to valor_do_mes;
create index valor_do_mes_comp on valor_do_mes(compromisso, mes);
