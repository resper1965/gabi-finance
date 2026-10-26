# ADR-029 · O que não é gasto, e "não é assinatura" sai do rol

Data: 26/10/2026 · Estado: aceito

**Contexto.** Gastos somava R$ 2,9 milhões desde set/2025, mas cerca de R$ 1,1 milhão era dinheiro que só trocou de lugar. Pagamento de fatura por boleto contava em dobro com as compras do cartão. Pix para a Bekaa, transferência para conta de investimento e aplicações também entravam como gasto. O `caixa.natureza` só reconhecia fatura quando a descrição dizia "fatura" ou a categoria era "credit card payment". No rol de assinaturas, marcar "não é assinatura" mudava o status mas deixava o item na lista, no total mensal e nos alertas. O Hermes não tinha como gravar nenhuma das duas coisas.

**Decisões (Ricardo, 26/10).**
1. **Boleto é gasto, salvo fatura de cartão.** É fatura quando bate com uma fatura conhecida (valor ±R$ 1, até 15 dias do vencimento) ou quando foi pago ao emissor de um cartão dele (Itaú/Personnalité, XP, Bradesco, Santander). Escola, condomínio, clube, seguro etc. continuam gasto.
2. **Transferência para conta própria ou para a Bekaa não é gasto.** A Bekaa entra pelo cadastro de empresas (`relacao: "pj_titular"`), não pelo código.
3. **Investimento não é gasto:** categoria "Investments", aplicação, transferência para conta investimento, chamada de margem.
4. **A marcação dele vence as regras.** Exemplo: o boleto Santander de R$ 169.851,90 (07/01/2026) é quitação de financiamento e fica como gasto.
5. **"Não é assinatura" e "encerrada" saem do rol:** lista padrão, total mensal, alertas e contador do menu. Seguem visíveis no filtro do próprio status, para desfazer.
6. **Hermes grava direto depois de mostrar o que vai mudar e ouvir o sim.**

**Como ficou.**
- Migração 0083: `lancamento.natureza_manual` ('gasto' | 'nao_gasto') e `lancamento.natureza_regra` (fatura, emissor, propria, investimento, manual).
- `gabi/dinheiro/nao_gasto.py` recalcula a natureza a partir do `caixa.natureza`, que segue intocado e coberto pelo golden. A captura chama a função depois de gravar todas as contas, porque o boleto do banco precisa das faturas dos cartões. Falha nessa etapa vira aviso da rodada, e a próxima tenta de novo.
- API: `gasto` (true/false/null) em `PATCH /lancamentos/{id}` e em `POST /lancamentos/lote`; cada lançamento traz `gasto: {valor, origem}`. Assinaturas trazem `no_rol`.
- Painel: em Gastos › Lançamentos, cada saída mostra se é gasto e por quê, com "é gasto / não é gasto / deixar o brain decidir"; em Cartões, a edição em lote tem "Gasto". Em Assinaturas, o filtro padrão é "No rol".
- MCP (escopo `fin`): `financeiro_marcar_gasto`, `assinaturas_listar`, `assinatura_marcar`. As escritas registram em `decisao` com origem `hermes`.

**Desfazer.** Ver o cabeçalho de `migrations/0083_nao_gasto.sql`. Depois, `git revert` do merge e reinstalar.
