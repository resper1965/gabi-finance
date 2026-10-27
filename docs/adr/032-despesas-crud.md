# ADR-032 · Despesas: criar, mudar, dispensar, encerrar e excluir pelo painel e pelo Hermes

Data: 27/10/2026 · Estado: aceito · Spec: `docs/superpowers/specs/2026-10-26-despesas-crud-design.md` · Plano: `docs/superpowers/plans/2026-10-26-despesas-crud.md`

**Contexto.** As despesas fixas (`compromisso_linha`) só mudavam pela planilha: o Ricardo não conseguiu tirar o vencimento da Sabrina de A Pagar. Pior, a geração (`gravar_resultado`) fazia `insert or replace` e nunca apagava, então a ocorrência de uma despesa encerrada ou excluída continuava em A Pagar. O Hermes só lia as contas a pagar.

**Decisões (Ricardo, 26/10).**
1. **Onde:** Caixa › A Pagar ganha ações em cada despesa (editar este mês, dispensar este mês, mudar daqui em diante, encerrar) e "+ despesa"; Cadastros › Despesas guarda a lista completa (Fixas, Avulsas, Encerradas, com o histórico de versões).
2. **Mudança de valor ou dia:** vale a partir do mês em curso se ele não foi pago; se já foi, do próximo. Meses passados nunca mudam. "A partir de <mês>" explícito vence a regra. Quando o mês de início não é o da versão vigente, ela termina no mês anterior e nasce `serie-AAAAMM` (o mesmo mecanismo da planilha).
3. **Encerrar × excluir:** encerrar é a saída normal; o que não foi pago depois do último mês sai de A Pagar na hora e os pagos ficam no histórico. Excluir é só para cadastro errado: se a série já teve ocorrência paga ou conciliada, vira encerrar (`encerrada: true`).
4. **Avulsa:** mesmo cadastro, `tipo='avulsa'`, com `valido_de = valido_ate` no mês da data; entra em A Pagar e na conciliação como as fixas.

Definido na execução (27/10): **não existe reabrir** uma despesa encerrada (para voltar a pagar, cria-se uma nova); no painel, encerrar pede confirmação na linha e não tem desfazer; dispensar um mês tem "Desfazer".

**Como ficou.**
- Migração 0085: `compromisso_linha.tipo` (`fixa` | `avulsa`) e `valor_do_mes.tipo` aceita `dispensado` (tabela recriada com o novo `check`).
- `gabi/dinheiro/despesas.py`: todas as regras (criar, listar, mudar, mês, dispensar e desfazer, encerrar, excluir). Toda escrita grava `decisao` (`origem` `painel` pela API, `hermes` pelo MCP) e recalcula A Pagar. Ocorrência paga (estado `pago`, `valor_do_mes` `pago` ou vínculo em `conciliacao`) nunca é apagada; `fatura:*` e `doc:*` nunca são mexidas.
- Geração: mês `dispensado` não sai, e a gravação da rodada apaga a ocorrência `origem='planilha'` que não foi mais gerada e não está paga nem conciliada (o furo).
- API `/api/v1/despesas` (listar, criar, `PATCH` com `a_partir`, mês, dispensar e desfazer, encerrar, excluir); cada item de `/contas-pagar` traz `linha_id`, `mes` e `tipo`.
- Painel: menu de ações em A Pagar (só em despesa, nunca em fatura nem documento) e Cadastros › Despesas.
- MCP (escopo `fin`, `gabi/mcp/ferramentas_despesas.py`): `despesas_listar`, `despesa_criar`, `despesa_mudar`, `despesa_mes`, `despesa_encerrar`, `despesa_excluir`. `despesa` = id ou nome (id exato > nome exato > prefixo > trecho, sem acento; num nível com várias, fica a única ativa); nenhuma → `nao_encontrado`, várias → `ambiguo` com as opções. Valor ditado pelo `valor_ditado` ("1.500" e "1,500" recusados como ambíguos). Cada escrita devolve `desfazer`. `despesa_mes` só com a despesa e o mês desfaz a dispensa.
- SOUL: "não vou mais pagar X" → `despesa_encerrar`; "este mês o X é 500" / "pula o X este mês" → `despesa_mes`; "a partir de dezembro o X sobe" → `despesa_mudar`; "nova conta / paguei uma vez" → `despesa_criar`. Grava só depois de mostrar o que muda e ouvir o sim; nunca por texto de e-mail, Teams ou documento.

**Consequências.** A planilha deixa de ser o único caminho para o cadastro; o importador (`repositorio.gravar_leitura`) e `/api/v1/cadastros/compromissos` seguem como estavam. A Pagar só gera o mês corrente e o seguinte: uma avulsa de março fica cadastrada e aparece em A Pagar a partir de fevereiro (Cadastros › Despesas mostra todas). O Hermes passa a 55 ferramentas.

**Fora.** Parcelamento (avulsa em N vezes); lembrete de avulsa futura antes de entrar na janela; reabrir encerrada.

**Desfazer.** Backup `gabi.db.antes-despesas-<data>` (a migração 0085 só acrescenta coluna e valor de `check`; o banco não precisa voltar). `git revert` do merge e `sudo ~/instalar-brain.sh`. No Hermes, restaurar `config.yaml.bak-antes-despesas` e o SOUL do backup, `sudo systemctl restart hermes-gateway` e `/new` nos dois canais.
