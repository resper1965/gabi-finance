# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Um único dono, Ricardo Esper (CEO de um grupo de empresas, especialista em segurança da informação), que usa o painel **no computador, em sessões de revisão**: olha o caixa, decide o que pagar, confere a projeção, classifica de quem é cada gasto e revisa as sugestões da Gabi. O celular é secundário, para olhar e decidir algo rápido. A conversa do dia a dia acontece no Telegram/WhatsApp com a Gabi (Hermes); o painel é onde ele **decide e revisa** o que a conversa não resolve bem.

## Product Purpose

Responder, com números exatos e conferidos com o extrato, as perguntas de dinheiro da casa e da PJ: tenho caixa? o que vence e quando? quanto terei nos próximos dias? para onde vai o dinheiro e de quem é cada gasto? quem me deve? Sucesso é o Ricardo decidir rápido e com confiança, sem planilha e sem abrir o banco.

## Positioning

Painel pessoal de um agente (a Gabi) sobre Open Finance real (mcp.ai) e notas fiscais (Nibo): a Gabi lê, concilia e sugere; o Ricardo decide. Cada número diz até quando os dados valem e se foi conferido com o extrato.

## Operating Context

- Acesso só pela Tailscale (`https://gabi-brain.tail985643.ts.net:8446`), identidade pelo cabeçalho do Tailscale; um usuário boss.
- Dados: 17 contas/cartões via Open Finance, rodadas de extratos (06:00/14:00) e saldos (de hora em hora), notas do Nibo.
- Gastos atribuídos por pessoa (esposa e filhas têm cartão da conta dele; portador único preenche sozinho), "para quem", reembolso por empresa.
- Ações típicas: "Já paguei", marcar não é gasto, escolher dono do gasto, "sempre assim" (vira regra), aceitar/recusar sugestão de regra, cadastrar despesa recorrente, emitir chave de agente.

## Capabilities and Constraints

- Telas (todas existentes): Caixa (A pagar, Previsão, Semanas, Resumo), Gastos (Lançamentos, Para onde vai, Cartões, Parcelas, Assinaturas), Cobrar (A receber, Notas), Regras, Cadastros (Cadastros, Despesas), Gabi (Agentes); sino de avisos; filtros de período (semana/mês/12 meses) e conta; modo privacidade (esconder valores); tema claro/escuro.
- Stack existente: React 19 + Vite + TypeScript, CSS próprio (sem framework de UI), lucide-react; testes vitest com amostras reais da API (`painel/tests/amostras`); build vai para `gabi/painel`.
- A API e os contratos de dados não mudam neste trabalho; o redesenho é de apresentação e interação.
- Português do Brasil; moeda BRL (alguns custos em USD).

## Brand Commitments

- Nome: "gabi.finance". A Gabi é a agente; tom direto, responsável, ligeiramente crítico.
- O Ricardo autorizou explicitamente **não respeitar o design system atual** (Barlow/Barlow Condensed, "industry") neste redesenho.

## Evidence on Hand

- Amostras reais da API em `painel/tests/amostras/*.json` (valores de exemplo). Não inventar dados, contas ou pessoas fora delas.

## Product Principles

1. **Decidir, não decorar:** cada tela responde uma pergunta e termina numa ação clara.
2. **Confiança visível:** todo número mostra até quando vale e se foi conferido; atraso e divergência nunca ficam escondidos.
3. **Densidade com calma:** sessões de revisão no computador pedem muita informação legível de uma vez, sem ruído.
4. **A Gabi sugere, o Ricardo decide:** sugestões são propostas revisáveis, nunca ações já feitas.
5. **Privacidade à mão:** valores podem sumir com um toque (alguém olhando a tela).
