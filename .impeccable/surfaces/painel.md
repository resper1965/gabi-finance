---
version: 1
slug: "painel"
primary_target: "painel"
related_targets: []
---

# Painel gabi-finance (todas as telas)

Scope: o painel inteiro (`painel/`), mode Operate. Público: o dono, no computador, em sessões de revisão; celular secundário. Tarefa: decidir e revisar dinheiro (caixa, a pagar, previsão, de quem é cada gasto, quem deve, sugestões da Gabi). Restrições: API, dados, rotas e ações não mudam; vitest e build continuam verdes; PT-BR; modo privacidade e tema escuro continuam.

## Direction contract

THESIS: Cada número é evidência. O painel é um laudo pericial do dinheiro: todo valor carrega sua proveniência (fonte, hora, conferido com o extrato ou não) e todo estado é um carimbo. Recusa o painel de banco digital de cards com número grande e gráfico decorativo.

OWN-WORLD: Laudo pericial forense. Fundo papel-de-laudo frio (cinza-esverdeado claro), tinta azul-grafite, trilho de navegação em grafite-toner profundo. Amarelo de etiqueta de evidência marca só o que está "a conferir". Carimbos: vermelho ATRASADO/DIVERGENTE, verde PAGO/CONFERIDO, azul NOTA. Sans de documentação técnica para tudo; mono só para códigos de item, horários e números de rodada. Regras finas de 1px, sem sombras de card, sem cantos arredondados grandes.

STORY: O dono abre, lê a conclusão do laudo (tem caixa? até quando?), vê os achados numerados com sua prova, resolve as pendências (pagar, classificar, revisar sugestão) e sai sabendo que os números foram conferidos.

FIRST VIEWPORT: Resumo: trilho grafite à esquerda; cabeçalho do laudo com a faixa de validade dos dados (até quando, rodada, conferida); "Conclusão" em uma frase grande; abaixo, tabela de Achados numerados (E-01…) com valor tabular, prova (fonte/conta) e carimbo de estado; à direita, Pendências do perito com a ação primária de cada uma; gráfico do saldo com o ponto de menor saldo marcado.

FORM: Laudo pericial (IMPECCABLE'S PICK, 1º da lista ordenada); seed:3780786ddbc7f550. Assinatura: a etiqueta de evidência — todo valor-chave tem código de item e, ao passar o mouse ou focar, mostra a cadeia de proveniência (fonte → rodada → conferência); estados como carimbos.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
