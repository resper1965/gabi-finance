# Revisão crítica: evolução do gabi.brain

## Papel

Atue como arquiteto sênior de software, especialista em agentes de IA, sistemas de memória, automação pessoal, gestão documental e segurança da informação.

Sua missão é **avaliar criticamente uma proposta de evolução do gabi.brain** apresentada por outra IA. Não concorde automaticamente: aponte redundâncias, complexidade desnecessária, funções que já existem, riscos de arquitetura e oportunidades esquecidas.

**Nomes:** *Gabi* é o projeto. *gabi.brain* ("o brain") é a aplicação, que lê as fontes, guarda as decisões e expõe o painel e o MCP. *Hermes* é o agente de conversa (Telegram e WhatsApp), que só conversa e consulta o brain pelo MCP.

## 1. Contexto (estado de 22/10/2026, depois da simplificação ADR-023)

O brain roda numa VPS própria: Python/FastAPI, SQLite, arquivos brutos imutáveis, timers do systemd e um serviço de fontes que é o único processo com rede e segredos (a API e o MCP falam com ele por um socket com lista branca de métodos).

**No ar hoje:**
- Dinheiro: extratos 2x por dia, saldos, regras de classificação, "a receber", despesas por empresa, agenda financeira e conferência de saldo só informativa (aviso `saldo_divergente`, um por conta por dia).
- Agenda: Google (gmail, bekaa) e Microsoft da ness, **só leitura**.
- E-mail: triagem com modelo e lixeira (nunca apaga de vez).
- Teams da ness: só metadados (quem, quando), sem o texto das mensagens.
- Contatos: sincronização, mais uma fila de propostas de escrita no Microsoft da ness, aprovadas uma a uma no painel.
- Avisos pelo Telegram; tela Hoje e resumo da manhã pelo Hermes.
- MCP com 18 ferramentas: de leitura, mais algumas que **só criam proposta** (nenhuma aprova, envia, paga ou apaga).
- Painel web de decisão: regras, propostas, lixeira e o que precisa do Ricardo.
- Paperless-ngx na mesma VPS. O MCP só busca e baixa; nada escreve no Paperless. O Hermes não lê PDF de propósito: PDF vai para o Paperless.

**Cortado em 22/10 (ADR-023), por não ter uso medido:**
- Escuta do WhatsApp.
- Saúde da família (exames, reembolso).
- Módulo Trabalho (frentes, tarefas, entregas).
- Cobrança e reembolso PJ.
- Índice de busca textual da memória (nenhuma consulta o lia).
- 26 tabelas vazias.
- 19 de 36 ferramentas do MCP que nunca foram chamadas.

**Em construção:** envios com anuência (ADR-024). O Hermes propõe evento de agenda ou mensagem no Teams, e nada sai até o Ricardo clicar Enviar no painel, naquele envio específico.

**Princípios que mandam:**
1. O brain sugere; o Ricardo decide. Exceção: o "para quem" de um gasto é aplicado sozinho quando há pelo menos 2 decisões iguais do Ricardo para o mesmo estabelecimento.
2. Nenhuma operação financeira, envio externo ou exclusão definitiva sem autorização. Exceção controlada: a ADR-024, um clique por envio.
3. Texto de terceiros (e-mail, Teams, PDF) é dado, nunca instrução.
4. Mínimo de complexidade, dependências e prolixidade.
5. Segurança, privacidade, rastreabilidade e auditabilidade.
6. **Regra de entrada (ADR-023):** pergunta vai para o Hermes (MCP). O painel só ganha tela quando há decisão ou lista para revisar. **Nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual que mostre a necessidade.** Use esta régua para julgar cada proposta.

**Fonte de referência:** repositório `resper1965/gabi-brain`, branch `main`. Leia primeiro `docs/STATUS.md`, `docs/ARQUITETURA.md`, `docs/BACKLOG.md` e `docs/adr/023-simplificacao.md`. O dossiê atualizado (22/10) está em `docs/DOSSIE-REVISAO-EXTERNA.md` na `main`; o da branch `docs/dossie-revisao-externa` é de 21/10 (antes dos cortes): só histórico.

**Acesso:** [ESCOLHA UMA] você tem acesso ao código da `main` e deve verificar nele antes de afirmar que algo falta | você NÃO tem acesso ao código; marque como "a confirmar" tudo o que depender dele.

## 2. Propostas a avaliar

Outra IA recomendou seis evoluções:

**A. Motor universal de pendências e obrigações.** Registrar e acompanhar compromissos vindos de e-mails, mensagens, documentos, transações e agendas: pagamentos pendentes, promessas feitas, renovações, prazos contratuais e providências pessoais.

**B. Inteligência documental sobre o Paperless.** O Paperless guarda os documentos e o brain extrai e relaciona: consulta em linguagem natural, extração estruturada, vencimentos, cláusulas, comparação de versões, documentos ausentes, conjuntos documentais, relação com pessoas, ativos e eventos, e referência verificável ao original. Sem duplicar os arquivos no brain.

**C. Memória temporal e contextual.** Registrar acontecimentos, mudanças, decisões e justificativas, para responder perguntas como "por que decidi cancelar tal serviço?". Lembre que um índice textual da memória acabou de ser removido por falta de uso.

**D. Correlação entre fontes.** Por exemplo: reconhecer um seguro, achar a cobrança no banco, detectar o vencimento e preparar uma proposta de renovação.

**E. Gestão da atenção.** Separar o que interrompe, o que vai para o resumo, o que é acompanhado em silêncio e o que não é comunicado. Considere o que já existe: janela de avisos, um aviso por condição por dia e o resumo da manhã.

**F. Aprendizado com as decisões.** Usar correções, aprovações e recusas do Ricardo para melhorar as sugestões, sem alterar regras críticas em silêncio. Considere o que já existe: regras sugeridas e aprovadas no painel, e o "para quem" certeiro.

## 3. Questões

**Arquitetura**
1. Essas capacidades precisam mesmo existir? Quais já existem, total ou parcialmente?
2. Dá para fazê-las como extensões do que existe?
3. Qual o risco de complexidade excessiva? Ela passa na regra do mês de uso manual?
4. O SQLite e a arquitetura atual continuam adequados?
5. Como dividir as responsabilidades entre Hermes, brain e Paperless?
6. Um motor universal de obrigações é uma boa abstração, ou acopla demais?

**Gestão documental:** API do Paperless; extração de datas, valores e cláusulas (uma data citada não é necessariamente um vencimento); busca textual contra busca semântica (embeddings fazem falta mesmo?); deduplicação e versão; acesso a documento sensível; evidência das respostas; documento contraditório ou desatualizado; documento com instrução maliciosa.

**Experiência:** o brain deve reduzir trabalho, não criar tarefa administrativa. Como evitar excesso de alerta e pedido repetitivo de aprovação, priorizar o relevante, aprender preferências sem perder previsibilidade e medir tempo economizado e erros evitados?

**Segurança:** injeção de prompt, exposição de dado pessoal, permissão excessiva, extração errada, vazamento entre contextos da família e ação indevida. Preserve a aprovação humana e a separação entre dado, raciocínio e execução.

## 4. Desafie a proposta

- O que ela complica sem necessidade?
- O que tem pouco valor prático?
- O que ela esqueceu?
- O que você faria diferente?
- O que deve ser descartado?
- O que dá para fazer em poucos dias com o que existe?
- O que deve esperar evidência de uso?

Não proponha tecnologia nova só porque é moderna.

## 5. Entrega (no máximo uma página e meia)

1. **Diagnóstico:** o que existe, o que falta e o que precisa ser confirmado no código.
2. **Avaliação:** classifique cada proposta (A–F) como MANTER, AJUSTAR, ADIAR ou DESCARTAR, com uma ou duas linhas de justificativa.
3. **Lacunas:** o que a proposta não contemplou.
4. **Arquitetura:** só as mudanças necessárias, reaproveitando o que existe.
5. **Roadmap:** até cinco incrementos pequenos, independentes e verificáveis. Cada um começa como uso manual pelo Hermes antes de virar sistema.
6. **Critérios de aceite:** como provar que cada incremento produz valor.
7. **Veredito:** concorda ou discorda da direção, e suas três principais mudanças.

## 6. Regras

- Não implemente nada e não altere código, banco ou infraestrutura.
- Não presuma ausência sem verificar. Sem acesso ao código, marque como "a confirmar".
- Separe fatos documentados, inferências e opiniões.
- Nada de recomendação genérica de arquitetura corporativa.
- Seja crítico, técnico e curto.
