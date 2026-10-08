-- 0006: Cadastros dos compromissos (substitui a planilha Google). Mesmas colunas da aba "Compromissos" do gabi-fin,
-- para a conciliação portada continuar recebendo exatamente a mesma entrada. Dinheiro em centavos (R7).
create table compromisso_linha(
  id text primary key,
  nome text not null,
  extrato text not null,
  apelidos text not null default '[]',   -- lista JSON
  vencimento text not null,              -- '5du' (5º dia útil) ou 'dia:N'
  ajuste_dia_util text not null default 'adia' check (ajuste_dia_util in ('adia','antecipa')),
  valor_tipo text not null default 'fixo' check (valor_tipo in ('fixo','variavel')),
  valor_padrao_centavos integer,
  forma text not null default '' check (forma in ('','pix','boleto','debito_automatico','fatura')),
  conta text not null default '', cartao text not null default '', documento text not null default '', pix text not null default '',
  ativo integer not null default 1,
  valido_de text, valido_ate text, obs text,
  linha_planilha integer,                -- ordem de origem (desempate estável)
  excluido_em text);

-- Parâmetros da conciliação (janela_antes_dias, tolerancia_*, horas_conta_parada, bancos_pj...). Valor em JSON.
create table parametro(chave text primary key, valor text not null);

-- "Valores do mês": valor confirmado ('valor') ou baixa manual ('pago') de um compromisso num mês.
create table valor_do_mes(
  id integer primary key,
  mes text not null,                      -- AAAA-MM
  compromisso text not null references compromisso_linha(id),
  tipo text not null check (tipo in ('valor','pago')),
  valor_centavos integer, vencimento text, data_pagamento text, origem text,
  linha_planilha integer);
create index valor_do_mes_comp on valor_do_mes(compromisso, mes);
