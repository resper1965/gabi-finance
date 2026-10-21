# As 7 caixas de e-mail (T3.3) — tabela `caixa_email`
Cadastro do Ricardo (Cadastros), nunca código (R6). Cada caixa tem: `endereco`, `provedor` (graph|google), `papel`, `empresa_id`, `como_entra`, `le`, `rascunho`, `frente_padrao_id`, `migra_para`, `ler_a_partir_de`, `estado` (`a_decidir` → `sim`/`nao`; só `sim` é lida) e `cursor` (historyId ou deltaLink).
- Guarda **só cabeçalho e trecho** (280 caracteres); corpo e anexo ficam na origem.
- `message_id` é único: o mesmo e-mail por Google e Graph (migração da ness) vira um item.
- Relevância: remetente conhecido (`pessoa.dados.emails`) ou palavra do parâmetro `email_palavras_relevantes`; sempre com motivo.
- Expurgo: só sugere, e só com uma `regra_expurgo` ligada pelo Ricardo.
- Quais são as 7 caixas e o provedor de cada uma: preencher em Cadastros no aceite T3.7.
