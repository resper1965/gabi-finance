-- 0013: "para quem" sem perguntar. Quem usa o cartão/conta, dono padrão da categoria e padrão por compromisso (dados do Ricardo, R6).
-- Favorecido (quem recebe) ≠ para quem (quem se beneficia): quem responde por uma filha fica em pessoa.dados.responsavel_por.
alter table conta add column usuarios text;                                  -- JSON: ids de pessoa que usam esta conta/cartão (NULL = não definido)
alter table categoria add column dono_padrao text references pessoa(id);     -- ex.: Mercado -> casa
create table compromisso_padrao(
  linha_id text primary key,                                                 -- compromisso_linha.id
  para_quem_id text references pessoa(id),
  categoria_id integer references categoria(id));
