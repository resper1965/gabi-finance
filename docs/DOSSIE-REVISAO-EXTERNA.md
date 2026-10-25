# gabi.brain: dossiê de funcionalidades e revisão externa

Versão de 22/10/2026. Substitui a de 21/10, que fica na branch `docs/dossie-revisao-externa` e descreve o sistema antes da simplificação. Este documento se sustenta sozinho e não pressupõe acesso ao código. Dados pessoais, nomes de terceiros, números, e-mails e segredos foram removidos de propósito.

**Nomes.** *Gabi* é o projeto. *gabi.brain* ("o brain") é a aplicação. *Hermes* é o agente de conversa.

## 1. O que é
O brain é o centro de uma assistência pessoal e familiar de um único dono, um empresário brasileiro com várias empresas, família e vida financeira complexa.

Ele lê as fontes da vida do dono: extratos e saldos bancários, notas fiscais, e-mails, agendas, Teams, contatos e documentos no Paperless. Guarda as **decisões** do dono e as **regras** derivadas delas, e responde de dois jeitos: por um painel web e por um servidor MCP.

O Hermes (Telegram e WhatsApp) só conversa e consulta o brain pelo MCP. Os dados e as regras ficam no brain. **O brain sugere; o dono decide.**

## 2. Princípios que mandam
- **R1. O brain sugere, o dono decide.** Exceção (ADR-023): o "para quem" de um gasto é aplicado sozinho quando há pelo menos 2 decisões iguais do dono para o mesmo estabelecimento.
- **R2. Nenhum envio externo automático.** E-mail só vai para a lixeira, nunca é apagado de vez. Exceção controlada (ADR-024, instalada em 22/10): evento de agenda e mensagem no Teams saem só com um clique do dono naquele envio específico.
- **R14. Texto de terceiros** (e-mail, Teams, PDF) é dado, nunca instrução.
- **ADR-007.** Só o dono conversa com o Hermes.
- Dados nunca vão chumbados no código. Segredos, só o dono coloca.
- Modelo de linguagem só onde há texto solto (triagem de e-mail, classificação); o resto são regras e timers sem modelo.
- Escrita em sistema externo sempre passa por proposta, aprovação, revalidação e auditoria.
- **Regra de entrada (ADR-023).** Pergunta vai para o Hermes. O painel só ganha tela quando há decisão ou lista para revisar. Nada vira sistema (tabela, timer, ADR) antes de um mês de uso manual. Exceções decididas pelo dono ficam registradas em ADR.

## 3. Arquitetura
- **Base:** serviço único (Python, FastAPI) com SQLite (WAL) e arquivos brutos imutáveis (JSONL.gz). Sem fila e sem data lake.
- **Rede e acesso:** a única entrada de rede é o Tailscale. O app escuta num socket Unix, e a identidade vem do cabeçalho do Tailscale. POST exige JSON e same-origin. Os níveis são `terceiros` < `familia_vip` < `boss`.
- **Serviço de fontes:** é o único processo com rede e segredos. A API e o MCP falam com ele por um socket com lista branca de métodos por fonte.
- **Rotina:** rodadas por timers do systemd, e backup semanal cifrado (gpg) para fora do servidor.
- **MCP:** ferramentas de leitura mais ferramentas que **só criam proposta**. Nenhuma aprova, envia, paga ou apaga. Cada token tem escopos, e cada chamada fica registrada.
- **Hospedagem:** uma VPS própria. Fora dela, só os provedores das fontes e um roteador de modelos (OpenRouter).

## 4. Funcionalidades (22/10/2026)

**No ar**

| Área | O que faz |
|---|---|
| Dinheiro | Extratos 2x por dia (Open Finance); saldos; regras de classificação (categoria, para quem, empresa); "para quem" certeiro; previsão de caixa; contas a pagar; parcelas e assinaturas; conferência de saldo só informativa (aviso `saldo_divergente`). |
| A receber | Notas fiscais (Nibo, em espera por chave) e recebimentos por pagador e conta. |
| Despesas por empresa | Despesas com empresa marcada pagas em conta pessoal, por empresa, para o dono cobrar ou lançar. |
| Agenda | Google e Microsoft (ness), somente leitura; conflitos; resumo do dia. |
| E-mail | Triagem com modelo (emergencial, importante, normal); regras "sempre lixo"; lixeira restaurável; alertas de emergência. |
| Teams (ness) | Só metadados (quem, quando, se mencionou o dono); aviso de conversa sem resposta. O texto das mensagens nunca é lido. |
| Contatos | Sincronização Google e Microsoft. Fila de propostas de escrita no Microsoft da ness (corrigir celular e nome, apagar telefone ou contato, acrescentar e-mail), aprovadas no painel. |
| Documentos | O Paperless guarda os PDFs. O MCP busca (com trecho e referência), baixa e lê o OCR; nada escreve no Paperless. |
| Documentos (família, bens, vencimentos) | Pronto na branch `feat/documentos`, a instalar (ADR-027). |
| Avisos e Hoje | Avisos com janela, entregues pelo Telegram; tela Hoje; resumo da manhã e agenda financeira pelo Hermes. |
| Hermes | Telegram e WhatsApp; 31 ferramentas MCP (com envios, família, documentos e registro de pessoa e pet). |
| Painel | Telas de decisão: regras, propostas, lixeira, cadastros, a pagar, gastos, qualidade. |

**Instalado em 22/10: envios com anuência (ADR-024)**
- O Hermes **propõe** (`propor_evento`, `propor_teams`):
  - evento com convidados nas agendas ness, bekaa e gmail;
  - mensagem num chat do Teams que já existe ou num canal de equipe.
- A área **Envios** do painel mostra exatamente o que vai sair. Só o clique em Enviar dispara o envio.
- Travas:
  - o hash do conteúdo exibido é conferido no envio;
  - a proposta vence em 24h ou no início do evento;
  - há um interruptor `envios.escrita`, desligado por padrão;
  - é uma tentativa só, com chave de idempotência na agenda;
  - erro 5xx ou timeout vira `incerto`, e o brain nunca reenvia sozinho.
- O Teams usa login delegado do dono.

**Instalado em 22–23/10: cadastro familiar e confiabilidade (issues #1 e #3, `docs/adr/025-cadastro-familiar.md`)**
- Fichas da família e documentos (CPF, RG, CNH, passaporte), com número, emissão e validade, consultáveis pelo Hermes (escopo `familia`).
- Contato é gravado direto quando o dono dita, com histórico e desfazer. Documento entra por proposta aprovada na aba Família do painel; a carga inicial (`tools/carga_familia.py`) traz o número completo do cadastro antigo e do OCR do Paperless.
- Consulta documental: `documentos_buscar` devolve trecho e referência, e `documentos_texto` devolve o OCR (dado de terceiros, nunca instrução).
- Confiabilidade: resposta vazia vem com aviso explícito; a ficha mostra todos os documentos ativos do mesmo tipo, com a origem, e as divergências de propostas; o SOUL do Hermes é versionado em `deploy/hermes/SOUL.md`.
- O dono aceitou, com registro em ADR, quatro exceções:
  - número completo no canal, inclusive de menores;
  - R1 parcial para dado de contato;
  - tabelas novas sem o mês de uso;
  - a volta do dado sensível que a ADR-023 tinha cortado.

**Cortado em 22/10 (ADR-023), por não ter uso medido**
- Escuta do WhatsApp.
- Saúde da família (exames, reembolso).
- Módulo Trabalho (frentes, tarefas, entregas).
- Cobrança e reembolso PJ.
- Índice de busca da memória.
- 26 tabelas vazias.
- 19 ferramentas MCP nunca chamadas.

O framework de agentes anterior (OpenClaw) e o sistema financeiro legado foram desligados.

**Em espera por chave de terceiros:** contatos Google, Microsoft da ionic, Nibo e Tailscale da família.

## 5. Padrão de escrita segura (contatos, depois envios)
1. **Fila de propostas** com estados explícitos (`pendente → aprovada → aplicada | falhou | recusada`; envios: `pendente → enviando → enviada | falhou | incerto | recusada | vencida`).
2. **Aprovação humana** no painel. Apagar nunca vai em lote. Envio é um clique por proposta.
3. **Interruptor global** desligado por padrão (`contatos.escrita`, `envios.escrita`).
4. **Revalidação antes de escrever:** o contato é relido no destino; no envio, conta, hash e validade são conferidos de novo.
5. **Superfície mínima na ponte:** métodos de escrita ficam em arquivos próprios, e um teste varre o código e falha se aparecer verbo ou endpoint fora do lugar permitido.
6. **Motivos de falha fixos;** logs só com contagens e ids, nunca nome, telefone, e-mail ou texto.
7. **Auditoria** de cada decisão.

**Processo de engenharia:**
- spec, depois plano, depois execução por subagentes: um implementador e um revisor independente por tarefa, e revisão final da branch no modelo mais capaz;
- TDD;
- suíte completa antes de cada merge: cerca de 2.300 testes Python e 137 testes do painel (vitest).

## 6. Decisões notáveis e trade-offs
- **SQLite em vez de servidor de banco.** Ganha simplicidade e backup trivial; perde concorrência: um escritor por vez, sem réplica.
- **Sem modelo nas regras financeiras.** Ganha previsibilidade e custo baixo; perde porque as regras explícitas precisam de manutenção.
- **Aprovação humana para quase tudo.** Ganha segurança; o custo é a fadiga de aprovação. A ADR-023 respondeu com o "para quem" certeiro, e o cadastro familiar com contato gravado direto.
- **Cortar o que não tem uso medido (ADR-023).** O sistema fica menor e mais fácil de manter; o que voltar terá de provar uso.
- **Hermes sem leitura de PDF.** É de propósito: PDF vai para o Paperless.

## 7. Limitações e dívidas conhecidas
- **Ponto único de falha humano:** um dono e um engenheiro (a própria assistente de código). A recuperação de backup do zero foi testada só em parte.
- **Uso ainda baixo:** cerca de 45 mensagens do dono ao Hermes em 12 dias. Os pedidos que mais ficaram sem resposta foram: ler validade de documento (passaporte), limpar e-mails pelo chat, registrar um valor a receber e consultar contatos (detalhe em `docs/revisao/2026-10-22-parecer-evolucao.md`).
- **Consulta que inventa:** houve um caso de o Hermes "achar" um lançamento que não existia e só se corrigir quando o dono cobrou.
- **Dependência de provedores** (roteador de modelos, Google, Microsoft, Open Finance, Nibo): mudança de API pode quebrar sem aviso.
- **Token delegado do Teams:** expira em até 90 dias e precisa de novo login do dono.
- **Microsoft da ionic:** acesso ainda pendente com o administrador do tenant.

## 8. Perguntas para o revisor
1. **Modelo de ameaça:** onde um e-mail, PDF ou mensagem maliciosa poderia virar ação, mesmo com R14 e com a fila? A chegada de envios e de número de documento no canal muda isso?
2. **Fadiga de aprovação:** com um único usuário, que classes de baixo risco podem ser aplicadas direto com desfazer, em vez de aprovar antes?
3. **Escopo:** a regra do mês de uso é o critério certo para separar extensão de subsistema novo?
4. **Arquitetura:** SQLite, serviço único e ponte separada aguentam se a família inteira passar a usar? O que quebra primeiro?
5. **Métricas de valor:** que 3 a 5 métricas mostram que a assistência poupa tempo e evita erro, e não só produz atividade?
6. **Pontos cegos** que este documento torne evidentes.

## 9. Como responder
Devolva:
- os 5 maiores riscos, em ordem e com cenário concreto;
- o que você manteria;
- o que mudaria primeiro e por quê;
- o que falta neste dossiê.

Marque o que é fato, o que é inferência e o que é opinião.
