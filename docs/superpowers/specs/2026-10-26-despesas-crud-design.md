# Despesas: criar, mudar, dispensar e encerrar pelo painel e pelo Hermes

Data: 26/10/2026 · Estado: desenho aprovado pelo Ricardo em 26/10 (item 3 da lista de 26/10) · ADR a criar: 032

## O que o Ricardo disse
- Não conseguiu apagar o vencimento da Sabrina: as despesas fixas não têm tela.
- Quer, pelo painel e pelo Hermes: criar, editar e encerrar despesa fixa; num mês só, dispensar, mudar o valor ou a data; despesa avulsa (uma vez só).
- Encerrar ou excluir tira de A Pagar, na hora, o que não foi pago.
- O Hermes grava depois do sim dele.

## Decisões (26/10)
1. **Onde (A):** Caixa › A Pagar ganha as ações em cada item e "+ despesa"; Cadastros › Despesas guarda a lista completa.
2. **Mudança de valor ou dia (A):** vale a partir do mês em curso se ele não foi pago; se já foi, a partir do próximo. Meses passados ficam como estavam. "A partir de <mês>" opcional.
3. **Encerrar × excluir (A):** encerrar é a saída normal ("a partir de <mês>"); o que não foi pago daí em diante sai de A Pagar na hora e os pagos ficam no histórico. Excluir só para cadastro errado; se a despesa já teve pagamento, vira encerrar.
4. **Avulsa (A):** mesmo cadastro, marcada `avulsa`, com data, valor e favorecido; entra em A Pagar e na conciliação com o extrato como as fixas.

## Estado de hoje (levantado)
- `compromisso_linha` (cadastro) já tem criar/editar/excluir na API (`/api/v1/cadastros/compromissos`), validação da planilha e **séries** de versão: `x`, `x-202611` e `x-202611-202703` são a mesma despesa, com `valido_de`/`valido_ate` sem sobreposição (`_serie`).
- `valor_do_mes` tem `tipo` `valor` (valor e/ou vencimento só daquele mês) e `pago` (baixa manual). Só `pago` tem rota (`POST /contas-pagar/{id}/paga`).
- `compromissos.gerar` cria as ocorrências do mês corrente e do seguinte; `repositorio.gravar_resultado` faz `insert or replace` e **nunca apaga**: ocorrência de despesa encerrada ou excluída fica em A Pagar (o furo).
- O Hermes só lê contas a pagar.

## Modelo (migração 0085)
- `compromisso_linha.tipo text not null default 'fixa' check (tipo in ('fixa','avulsa'))`.
- `valor_do_mes.tipo` aceita também `dispensado` (recria a tabela com o novo `check`, copiando as linhas).
- **Avulsa** = linha `tipo='avulsa'` com `valido_de = valido_ate = AAAA-MM` e `vencimento='dia:N'`. Id gerado pelo nome + mês (`slug-AAAAMM`).

## Regras (`gabi/dinheiro/despesas.py`, novo; usado pela API e pelo MCP)
- `mes_inicial(con, serie, hoje)`: mês em curso se a ocorrência dele não está paga (estado `pago` ou `valor_do_mes` `pago`); senão o próximo.
- `mudar(con, id, campos, a_partir=None, hoje)`: se `a_partir` (ou `mes_inicial`) é igual ao `valido_de` da versão vigente, ou ela nunca gerou mês pago, edita a própria linha; senão encerra a versão vigente no mês anterior e cria `serie-AAAAMM` com os campos novos (o mesmo mecanismo da planilha). Campos: nome, valor padrão, vencimento, forma, conta/cartão, extrato, apelidos, pix.
- `mudar_mes(con, id, mes, valor=None, vencimento=None)`: grava/atualiza `valor_do_mes` `valor`.
- `dispensar_mes(con, id, mes)`: grava `valor_do_mes` `dispensado`; desfazer = remover a linha.
- `encerrar(con, id, ultimo_mes=None, hoje)`: `valido_ate` = `ultimo_mes` ou o mês anterior a `mes_inicial`. Nunca apaga linha.
- `excluir(con, id)`: só se a série nunca teve ocorrência paga ou conciliada; senão chama `encerrar` e devolve `{"encerrada": true}`.
- `criar_avulsa(con, nome, data, valor, forma, extrato, ...)` e `criar_fixa(...)` (passam pela mesma validação de `Compromissos._validar`).
- Toda função termina recalculando (`atualizar_compromissos`), como os cadastros já fazem.

## Geração e o furo
- `gerar` pula o mês com `valor_do_mes` `dispensado`.
- `gravar_resultado` passa a apagar, dos meses gerados na rodada, as ocorrências `origem='planilha'` que **não** vieram na rodada **e** não estão pagas nem têm vínculo em `conciliacao` (apaga também o vínculo `manual:` órfão, se houver). Ocorrência paga fica sempre.

## API
- `POST /api/v1/despesas` (fixa ou avulsa), `PATCH /api/v1/despesas/{id}` (com `a_partir` opcional), `POST /despesas/{id}/mes/{AAAA-MM}` (valor/data), `POST /despesas/{id}/mes/{AAAA-MM}/dispensar` e `DELETE` dele (desfaz), `POST /despesas/{id}/encerrar` (`ultimo_mes` opcional), `DELETE /despesas/{id}` (exclui ou encerra).
- `GET /api/v1/despesas?tipo=fixa|avulsa&situacao=ativa|encerrada`: lista por série (versão vigente + histórico de versões), próximo vencimento e valor.
- Cada item de `GET /contas-pagar` traz `linha_id`, `mes` e `tipo` para a tela chamar as ações.
- `/cadastros/compromissos` continua como está (compatibilidade); as telas novas usam `/despesas`.

## Painel
- **Caixa › A Pagar:** em cada despesa (não em fatura nem documento avulso), menu "Editar este mês · Dispensar este mês · Mudar daqui em diante · Encerrar". Botão "+ despesa" com escolha Fixa/Avulsa. Dispensado some da lista com "desfazer" por alguns segundos.
- **Cadastros › Despesas:** abas Fixas, Avulsas e Encerradas; editar, encerrar, excluir; histórico de versões da série.

## Hermes (escopo `fin`)
- `despesa_criar(nome, valor, dia ou data, avulsa, forma?, ...)`, `despesa_mudar(id, campos, a_partir?)`, `despesa_mes(id, mes, valor? / vencimento? / dispensar?)`, `despesa_encerrar(id, ultimo_mes?)`, `despesa_excluir(id)`, `despesas_listar(...)`.
- Cada uma grava direto **depois** de mostrar o que muda e ouvir o sim; registra em `decisao` (origem `hermes`). Nome ambíguo devolve `ambiguo` com as opções.
- SOUL: "não vou mais pagar X" → `despesa_encerrar`; "este mês o X é 500" → `despesa_mes`; "a partir de dezembro o X sobe" → `despesa_mudar`. Lista oficial em `docs/fontes/hermes.md` e include do config.

## Testes
- Regras: `mes_inicial` (pago/não pago), mudar com e sem versão nova, mudar_mes, dispensar e desfazer, encerrar, excluir sem e com pagamento, criar avulsa.
- Geração: mês dispensado não sai; furo (encerrar/excluir/dispensar apaga a não paga e mantém a paga e a conciliada).
- API de ponta a ponta e A Pagar trazendo `linha_id`/`mes`.
- MCP: cada ferramenta, `ambiguo`, escopo; lista oficial e SOUL.
- Painel: ações no A Pagar, "+ despesa", abas de Cadastros › Despesas.

## Limite conhecido
A Pagar só gera o mês corrente e o seguinte: uma avulsa de março fica cadastrada e aparece em A Pagar a partir de fevereiro. Cadastros › Despesas mostra todas.

## Fora
- Parcelamento (avulsa em N vezes).
- Lembrete de avulsa futura antes de entrar na janela.

## Desfazer
Backup `gabi.db.antes-despesas-<data>`; `git revert` do merge e reinstalar; Hermes: config e SOUL dos backups, restart e `/new`.
