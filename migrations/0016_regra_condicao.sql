-- 0016: regra com condição opcional (conta, faixa de valor, dia da semana), em JSON: {"conta_id":[1],"valor_min":1000,"valor_max":5000,"dias_semana":[5,6]}.
-- Valores em centavos (valor absoluto); dia da semana 0=segunda … 6=domingo. NULL = regra sem condição (como antes).
alter table regra add column condicao text;
