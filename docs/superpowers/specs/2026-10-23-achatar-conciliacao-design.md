# Achatar compromissos e conciliação

Data: 23/10/2026 · ADR: `docs/adr/026-conciliacao-achatada.md` (a escrever junto com o código) · Item: primeiro do "Depois" no `docs/BACKLOG.md`

## Objetivo
Reduzir o código que mantemos. Hoje a tela A pagar funciona; o motivo é só manutenção (decisão do Ricardo, 23/10). `compromissos.py` (225 linhas) e `conciliacao.py` (360) foram portados do gabi-fin sem alterar a lógica: 6 estados, 8 regras de casamento, valores em float, para cerca de 27 linhas por mês. A paridade com o gabi-fin não tem mais valor (o gabi-fin saiu).

## Decisões do Ricardo (23/10)
1. Caminho **A**: 4 estados e regras simples; os consumidores se ajustam.
2. Antes de instalar, comparar o antigo com o novo nos dados reais e mostrar o que mudou.
3. Os testes golden do gabi-fin saem; entram testes próprios.

## Fora do escopo
- Esquema do banco: `compromisso` e `conciliacao` ficam como estão (a coluna `estado` não tem restrição). Só uma migração de dados (0080) leva as linhas antigas, fora da janela da rodada, de `previsto`/`debito_automatico` para `aberto`.
- Planilha: as colunas e os parâmetros continuam sendo lidos. `tolerancia_juros` passa a ser ignorado (continua aceito, para a planilha não quebrar).
- Cálculo do vencimento (`vencimento_do_mes`, `vencimento_util`), regras de documento e de fatura em `compromissos.gerar`: só mudam para centavos.

## 1. Estados

| estado | quando |
|---|---|
| `pago` | casou com o extrato, fatura `PAID` no banco, ou baixa manual ("Já paguei") |
| `atrasado` | `vencimento_util` < hoje e nada casou |
| `aberto` | não venceu; débito automático sem lançamento fica aqui sempre (nunca atrasado) |
| `a_conferir` | casou mas o valor não confere, ou venceu com o extrato parado |

Saem `previsto` (vira `aberto`; o valor estimado continua visível por `valor_fonte` em `padrao`/`ultimo`/nulo) e `debito_automatico` (vira `aberto`; reconhecido por `forma == "debito_automatico"`).

## 2. Casamento (`gabi/dinheiro/conciliacao.py`, reescrito)
Assinatura mantida: `conciliar(comps, txs, vinculos, estado_contas, pagos, params, hoje, agora, donos=None) -> (resultado, novos)`. Valores em centavos (int) em toda a função.

1. **Vínculo gravado** (`conciliacao`, menos `manual:`): o compromisso fica `pago` com aquele lançamento; o lançamento sai do jogo.
2. **Lançamentos candidatos:** débito (`valor < 0`) de conta BANK não PJ, data até hoje, sem natureza `neutro` (transferência própria, como hoje), não vinculado.
3. **Por favorecido:** compromissos em ordem de (`vencimento_util`, `id`). Cada um pega, entre os candidatos livres na janela (`vencimento_util - janela_antes_dias` até hoje) cuja descrição contém alguma `extrato_chaves` ou, se é fatura, o nome do cartão num pagamento de fatura (`_casa_emissor`, mantido), o de data mais próxima do `vencimento_util`; empate, o de id menor. A ordem por vencimento faz o Pix atrasado ficar com o mês vencido.
4. **Por valor**, para quem sobrou com valor: candidato livre na janela, que não contém chave de nenhum compromisso, com `|valor - pago| <= tolerancia_valor`; pagamento de fatura (`caixa.FATURA_RE`) só paga fatura. Mesma ordem e mesmo critério de proximidade.
5. **Valor do casamento:** fixo ou confirmado (`valor_fonte` em `valores_do_mes`/`documento`/`fatura`): `|dif| <= tolerancia_fixo * valor` = `pago`; fora = `a_conferir` com motivo ("pago a menor: R$ x de R$ y"; fatura: "pago a menor (mínimo?)"; acima: "pago acima: ..."), e o vínculo não é gravado. Variável estimado ou sem valor: `pago` com qualquer valor.
6. **Sem lançamento**, na ordem: fatura `PAID` = `pago` (método `banco`); baixa manual (Valor tipo `pago` da linha no mês) = `pago` (`manual:<id>`, como hoje); `forma == "debito_automatico"` = `aberto`; venceu e extrato parado (`_parada`, mantida) = `a_conferir`; venceu = `atrasado`; senão `aberto`.

Saem: atribuição gulosa global com ordenação por certeza da série (`_ordenar`, `_atribui`, `_certeza`), faixa de juros e o campo `juros`, regra do nome de cartão ambíguo, regra "perdeu no empate", prioridade "já vencido" da baixa manual. O resultado por compromisso mantém `estado, metodo, tx_id, pago_em, diferenca, motivo` (diferença em centavos).

Meta: cerca de 150 linhas.

## 3. Compromissos (`gabi/dinheiro/compromissos.py`)
- Valores em centavos (`valor`, totais de fatura, valor de documento, último pagamento).
- `repositorio.py` deixa de converter float↔centavos para a conciliação (`_real`/`_cent` só onde a fonte ainda é float).
- Sai código duplicado de chaves entre `compromissos.py` e `conciliacao.py` (uma função só para "descrição contém chave").
- Meta: cerca de 170 linhas.

## 4. Consumidores
| arquivo | ajuste |
|---|---|
| `gabi/dinheiro/contas_pagar.py` | grupo `debito_automatico` por `forma`; sem `previsto`; diferença já em centavos |
| `gabi/dinheiro/projecao.py` | saída com atraso = `aberto`/`atrasado` sem débito automático; débito automático por `forma`, só no dia e se a data não passou |
| `gabi/avisos.py` | `aberto` no lugar de `aberto`/`previsto`; marca `debito_automatico` pela `forma`; `ABERTOS_A_VENCER` = (`aberto`,) |
| `gabi/dinheiro/agenda_financeira.py`, `gabi/rotas/*`, `gabi/mcp/*` | trocar qualquer teste de `previsto`/`debito_automatico` como estado |
| `painel/src/telas/Caixa/APagar.tsx`, `Resumo.tsx`, `Gastos/Assinaturas.tsx` | o mesmo; o grupo "Débito automático" continua |

A lista exata sai de `grep -rn "previsto\|debito_automatico\|juros"` no plano.

## 5. Comparação antes de instalar
`tools/comparar_conciliacao.py <cópia do banco>`: roda `gerar`+`conciliar` antigo (copiado para `tools/_conciliacao_antiga/`, apagado depois da instalação) e novo sobre a mesma cópia, sem gravar, e imprime só os compromissos cujo estado mudou: id, nome, vencimento, estado antigo → novo, motivo. Não listar as trocas esperadas `previsto → aberto` e `debito_automatico → aberto`. O Ricardo roda com `!` (o Claude não lê o banco de produção) e confere a lista antes do merge.

## 6. Testes
- Saem `tests/golden/compromissos.json`, `tests/golden/cenarios.json` e os testes que os leem (`test_golden_cenarios.py` e o trecho de compromissos de `test_pipeline_compromissos.py`, se só servirem à paridade).
- Entram testes em `tests/dinheiro/test_conciliacao.py`, um por regra da seção 2: vínculo gravado; transferência própria fora; favorecido na janela e fora; Pix atrasado fica com o mês vencido; dois meses e um lançamento; por valor e pagamento de fatura só em fatura; fixo pago a menor e acima; variável qualquer valor; fatura PAID; baixa manual com e sem lançamento; débito automático nunca atrasado; extrato parado; vencido = atrasado; não vencido = aberto.
- Os casos reais que os golden cobriam viram testes nomeados.
- Suíte inteira verde (pytest e vitest), lendo o resumo do pytest.

## Pronto quando
1. `conciliacao.py` + `compromissos.py` com cerca de 320 linhas no total (hoje 585).
2. Suíte verde.
3. Lista da comparação conferida pelo Ricardo, sem compromisso pago virando atrasado no mês corrente sem motivo aceito.
4. Instalado, e a rodada de extratos seguinte com `conferida=True` e a tela A pagar abrindo.
