# Aceite da Fase 2 (T2.10) — situação em 10/10/2026

**Estado: NÃO aceita ainda.** Este documento é o esqueleto honesto do aceite: o que está no ar, o que falta medir e quem decide (G20).

| # | Critério (plano mestre T2.10) | Situação | Como fechar |
|---|---|---|---|
| 1 | ≥ 80 % dos itens de reembolso com comprovante casado automaticamente | **Não medido.** A conciliação existe (`gabi/cobrar/comprovantes.py`, propostas + confirmação), mas depende de comprovantes reais no Paperless (G18). | Com dados reais: `select 1.0*sum(estado='confirmado' or confianca>=0.9)/count(*) from comprovante_vinculo` ≥ 0,80; colar o número aqui. |
| 2 | Lote Nibo roda 2 vezes sem duplicar, em conta real, com a confirmação do Ricardo | **Coberto por teste** (`tests/cobrar/test_lote_nibo.py`: repetir não duplica); **não rodado em conta real** (G19). | Ricardo confirma o lote no painel (Reembolsos → Bekaa), roda de novo e confere no Nibo. |
| 3 | Pedido real chega pelo canal de teste e aparece em Pedidos | **Adiado para o plano do gabi-agent (Hermes), por decisão do Ricardo.** A tela e a API de Pedidos existem e são testadas; falta só o canal. | Fica como pendência do plano gabi-agent; o G20 aceita a Fase 2 sem este item. |

## No ar
Notas a receber (NFS-e da Bekaa importadas), previsão de caixa e recebimentos propostos, reembolsos por empresa (agora cobrando só os itens selecionados), lote do Nibo, comprovantes e pedidos (API + telas).

## Pendente
G18 (comprovantes reais), G19 (lote em conta real), G20 (Ricardo aceita a Fase 2 sem o item 3). Quando 1 e 2 estiverem medidos, atualizar a coluna "Situação" e a primeira linha deste arquivo.
