# ADR-031 · Reembolso por compra (Empresa do lançamento)

Data: 26/10/2026 · Estado: aceito

**Contexto.** Uma compra no cartão do Ricardo que a NESS, a Bekaa ou a IONIC devolvem precisa contar em "Despesas por empresa" (`despesas_por_empresa`). O campo é a **Empresa** do lançamento, que não tem nada a ver com "quem gastou" (ADR-030). Até agora ele só era marcado pelo lote de Cartões, e o Hermes apenas propunha (`classificar_lancamento`). O lote ainda tinha um bug: mandava `Number("ness")`, que vira NaN, depois `null` no JSON, e a empresa era limpa.

**Decisões (Ricardo, 26/10).**
1. Em Gastos › Lançamentos, cada compra (saída) tem "Reembolso: pessoal / <empresa>", que grava a Empresa só daquela compra (origem `voce`).
2. O Hermes grava direto com `financeiro_marcar_reembolso(lancamento_ids, empresa)` (escopo `fin`), depois de mostrar a compra e ouvir o sim. "pessoal" tira a empresa. Nome ambíguo devolve `ambiguo`; IONIC sem país é `ionic-health-br`. A escrita fica registrada em `decisao` com origem `hermes`.
3. A compra continua sendo gasto do Ricardo. Não volta nada da cobrança nem do reembolso PJ cortados na ADR-023: o Ricardo cobra ele mesmo.

**Consequências.** O lote de Cartões passa a mandar o id de texto. A guarda do SOUL (que impede a volta da promessa "PDF entra no fluxo de exames/reembolso") passa a aceitar "reembolso" só nas linhas desta ferramenta e de `despesas_por_empresa`.
