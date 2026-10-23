# ADR-026 · Conciliação achatada (4 estados, centavos)

Data: 23/10/2026 · Estado: aceito · Spec: `docs/superpowers/specs/2026-10-23-achatar-conciliacao-design.md`

**Contexto.** `compromissos.py` e `conciliacao.py` foram portados do gabi-fin sem mudar a lógica: 6 estados, 8 regras de casamento, valores em float, para cerca de 27 linhas por mês. A tela A pagar funcionava; o motivo foi só manutenção. A paridade com o gabi-fin não tem mais valor (o gabi-fin saiu).

**Decisão.**
1. **4 estados:** `pago`, `atrasado`, `aberto`, `a_conferir`. `previsto` e `debito_automatico` deixam de ser estado: viram `aberto`; o débito automático é reconhecido pela `forma` e nunca fica atrasado.
2. **Casamento simples:** vínculo gravado; por favorecido (ou emissor da fatura) na janela; por valor para quem sobrou. Compromissos em ordem de vencimento. Entre os candidatos, o cujo valor encaixa (seria `pago`) ganha primeiro, depois a data mais próxima do vencimento útil, depois o menor id.
3. **Centavos (int)** em todo o caminho. Os valores de baixa manual (`pagos`) são convertidos por `compromissos.valores_em_centavos` antes de `conciliar`; `conciliar` não converte nada.
4. **Migração 0080 só de dados:** linhas antigas `previsto`/`debito_automatico` viram `aberto`. Esquema intocado.
5. **Testes próprios** no lugar dos golden do gabi-fin.

**Consequências.**
- Sem faixa de juros: `tolerancia_juros` continua aceito na planilha, mas é ignorado. Pagamento acima do valor, mesmo dentro da antiga faixa, vai para `a_conferir` ("pago acima: ..."), por exemplo condomínio R$ 840 de R$ 800.
- Duas passadas: valor conhecido que encaixa casa antes da estimativa, para que o Pix de outro compromisso do mesmo favorecido não seja levado.
- Fatura `PAID` e baixa manual valem sobre um casamento `a_conferir`.
- Casamento por valor (dentro de `tolerancia_valor`) é `pago`, sem conferência de tolerância.
- Sem paridade com o gabi-fin; a comparação em produção (23/10) deu 0 diferenças, fora as trocas esperadas para `aberto`.
- Fica de fora a atribuição global por certeza da série, o campo `juros` e as regras de cartão ambíguo e de "perdeu no empate".
- Tamanho: `compromissos.py` + `conciliacao.py` de 585 para 423 linhas (-28%), medido com `wc -l`. A meta de cerca de 320 não foi alcançada; cortar mais prejudicava a leitura, e o tamanho foi aceito.
- Ferramentas temporárias saem depois da instalação (BACKLOG CA1): `tools/_conciliacao_antiga/`, `tools/comparar_conciliacao.py`, `tests/test_comparar_conciliacao.py` e, fora do repositório, `~/comparar-conciliacao.sh`.
