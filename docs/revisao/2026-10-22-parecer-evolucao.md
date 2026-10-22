# Parecer: evolução do gabi.brain (propostas A–F) · 22/10/2026

Legenda: **[F]** fato verificado no código ou na doc (`main`, salvo indicação) · **[I]** inferência · **[O]** opinião.

## 1. Diagnóstico
- **[F] Boa parte de A, D, E e F já existe.** Compromissos (planilha, faturas e documentos, `gabi/dinheiro/compromissos.py`, `compromisso_linha`), contas a pagar e atrasadas (`contas_pagar.py`), entradas esperadas que não caíram (`esperados.py`), assinaturas inativas (`assinaturas.py`), aviso `cobrada_apos_cancelar` (`avisos.py`), evento mensal "pagar" na agenda que vira pergunta (`sugestoes_agenda.py`), pergunta de dono por fornecedor (`sugestoes_dono.py`, até 5 abertas), regras sugeridas e aprovadas e o "para quem" certeiro (ADR-023 §6).
- **[F] Atenção:** um aviso por (tipo, chave) por dia; tipos `SEMANAL` com 7 dias de silêncio; janela de entrega de 2 dias (`avisos.py`, `telegram.py`); e-mail com prioridade de 0 a 3 (`email_listar`); resumo da manhã (`ferramentas_dia.py`).
- **[F] O Paperless hoje está quase desligado do brain.** `documentos_buscar` devolve só id, título e data (`gabi/mcp/ferramentas_prop.py`). `documentos_baixar` entrega o PDF em base64, que o Hermes não lê de propósito. `compromissos.gerar` aceita documentos, mas a rodada chama `atualizar_compromissos(con, hoje, agora)` sem `docs` (`dinheiro/rodar.py:66`). A ponte só permite `docs` e `baixar` (`fontes/ponte.py:24`).
- **[F] Memória:** a tabela `memoria` (7.438 linhas, legada e sem código) e a `decisao` (`quem`, `o_que`, `origem`, sem campo de justificativa, `migrations/0001_base.sql`).
- **[F] Correção ao contexto:** `decisao_responder` (`ferramentas_dec.py`) registra a escolha do Ricardo e aplica o efeito, que vem de uma lista fechada (`gabi/decisoes.py`). Logo, não é verdade que nenhuma ferramenta MCP decide: esta grava uma decisão vinda do chat.
- **A confirmar:** com qual usuário e permissões o token do Paperless entra; se há documentos sensíveis (saúde, filhas) acessíveis a esse token.

## 2. Avaliação
| | Classe | Justificativa |
|---|---|---|
| **A** Motor universal | **DESCARTAR** (como motor) | [F] As obrigações financeiras já existem e o BACKLOG ("Depois") até quer **achatar** compromissos (cerca de 27 linhas por mês). [O] Um modelo genérico de "promessa, prazo, providência" acopla e-mail, agenda, banco e documento num esquema só, e não passa na regra do mês. Renovação e vencimento cabem em `compromisso_linha`. |
| **B** Inteligência documental | **AJUSTAR** | [O] Vale a parte mínima: o Hermes achar e citar o documento (id e trecho do OCR). Extração de cláusulas, comparação de versões e "documentos ausentes" ficam fora. Quem guarda os metadados (tipo, correspondente, campo "vencimento") é o próprio Paperless, preenchidos pelo Ricardo ou pelas regras do Paperless, nunca extraídos por modelo. |
| **C** Memória temporal | **ADIAR** | [F] O FTS saiu por falta de leitura e a `memoria` ficou órfã. [O] "Por que cancelei X?" ainda não apareceu como pergunta real. Antes de criar tabela, o assistente procura no histórico do Hermes as perguntas desse tipo (sem trabalho do Ricardo). |
| **D** Correlação | **ADIAR** (o genérico) | [I] O exemplo do seguro já se resolve com assinatura + compromisso + o campo de vencimento do Paperless. [O] Um motor de correlação entre fontes multiplica falsos positivos, a mesma doença da conferência de saldo que a ADR-023 matou. |
| **E** Atenção | **AJUSTAR** | [F] O mecanismo existe. [O] Falta calibrar, não uma camada nova: os itens do BACKLOG "Depois" (tirar do emergencial os e-mails do próprio sistema; agenda diária sem LLM). |
| **F** Aprendizado | **AJUSTAR** | [F] Já há aprendizado com trava: regras aprovadas e o certeiro. [F] Havia 113 sugestões nunca decididas (ADR-023). [O] O que falta é medir a taxa de decisão por tipo de pedido e cortar os que ninguém responde. Nenhum aprendizado novo "em silêncio". |

## 3. Lacunas da proposta
1. **[F] Não há como medir o "mês de uso manual".** `chamada_mcp` guarda ferramenta, status e duração, mas não a pergunta nem o que ficou sem resposta (`servidor.py:_registrar`). Sem isso, a régua da ADR-023 vira opinião.
2. **Custo de atenção dos pedidos de aprovação:** perguntas, sugestões, propostas de contato e agora envios (ADR-024) concorrem pelo mesmo Ricardo. A proposta só soma filas.
3. **[I] Vazamento de documento sensível:** `documentos_baixar` manda o PDF inteiro ao Hermes e daí ao provedor do modelo, sem passar pela `matriz_acesso` (que só cobre o painel e a API, `identidade.py:70`). O controle tem de estar no usuário do Paperless (permissões e etiquetas), não no prompt.
4. **Injeção por documento:** devolver trecho de OCR aumenta a superfície de ataque. Mitigação: as ferramentas continuam só de leitura, o envelope já marca o conteúdo como dado, e trecho de documento nunca alimenta `decisao_responder` nem as ferramentas de proposta.
5. **Datas:** uma data citada não é vencimento. Por isso o vencimento é campo explícito, nunca inferido de texto.

## 4. Arquitetura (só o necessário)
- [O] **Nada de banco vetorial, embeddings ou fila nova.** SQLite em WAL com um escritor e esse volume continua adequado. A busca textual do próprio Paperless (OCR) basta até prova em contrário.
- Divisão: **Paperless** = arquivo, OCR e metadados documentais (fonte da verdade). **Brain** = fatos financeiros, decisões e o id do documento Paperless como referência. **Hermes** = conversa, sem estado próprio.
- Única mudança de código no curto prazo: `documentos_buscar` passa a devolver um trecho limitado (cerca de 300 caracteres de destaque ou `content`) e o link do original. Não cria tabela, timer nem ADR.

## 5. Roadmap (cada item começa manual)
1. **Lacunas a partir do histórico (zero código, zero trabalho do Ricardo):** o assistente lê as conversas que o Hermes já guarda (desde 10/10) e lista as perguntas que ficaram sem resposta, cada uma ligada a uma proposta A–F. Depois repete a leitura 7 dias mais tarde.
2. **Busca com trecho e citação** em `documentos_buscar` (descrita na seção 4). O uso é manual pelo Hermes desde o primeiro dia.
3. **Vencimento no Paperless:** o assistente lê o OCR de cerca de 10 apólices e contratos e propõe o campo "vencimento" de cada um. O Ricardo só confirma, e o Hermes consulta pela busca. Só com uso comprovado se liga o `docs` já previsto em `atualizar_compromissos`.
4. **Placar de pedidos (só SQL de leitura):** taxa de decisão e tempo até decidir por tipo (`sugestao`, `pergunta`, propostas de contato, `envio_proposta`).
5. **Calibrar avisos** com os dois itens de atenção do BACKLOG "Depois".

## 6. Critérios de aceite
1. No histórico atual mais 7 dias, há pelo menos 10 lacunas. Proposta sem lacuna registrada é arquivada.
2. Pelo menos 5 perguntas de documento respondidas com id verificável, sem precisar de `documentos_baixar`, e zero trecho tratado como instrução.
3. Pelo menos uma renovação vista com 15 dias de antecedência, que antes passaria despercebida.
4. Todo tipo de pedido com taxa de decisão abaixo de 50% em 7 dias é cortado ou vira lote semanal.
5. Avisos por semana no Telegram caem pelo menos 30%, sem nenhum caso de "devia ter avisado" anotado no diário.

## 7. Veredito
Discordo da direção e concordo com o problema. A proposta descreve uma plataforma (motor universal, correlação, memória, inteligência documental) logo depois de uma ADR que cortou metade do sistema por falta de uso, e ignora que obrigações financeiras, atenção e aprendizado já existem. Minhas três mudanças: **(1)** em vez de motores novos, estender pontualmente o que existe (`compromisso_linha` e `assinaturas` para renovações; `documentos_buscar` com trecho e citação); **(2)** instrumentar a regra do mês antes de qualquer sistema, com o diário de lacunas do Hermes e o placar de taxa de decisão dos pedidos; **(3)** deixar o Paperless como dono dos metadados documentais (vencimento como campo explícito, permissões do token restritas), sem extração por modelo nem embeddings, e com o brain só referenciando o id do documento.

## Anexo: evidência do histórico do Hermes (10/10 a 22/10, lida pelo assistente)
Volume: cerca de 45 mensagens reais do Ricardo em 12 dias (Telegram e WhatsApp); o resto são crons e testes.

| Pedido que ficou sem resposta | Vezes | Proposta |
|---|---|---|
| Ler um PDF mandado no chat (18/10, duas vezes) e "quando vence meu passaporte" (22/10: achou o documento no Paperless, mas não conseguiu ler a validade) | 3 | **B**: a evidência mais forte; o caso do vencimento é real |
| "Apague esses e-mails" / "elimine os alertas do GitHub" (o Hermes não tem como propor uma regra "sempre lixo" nem mandar para a lixeira) | 2 | **E**, mais ação com anuência |
| Registrar um valor "a receber" (o Pix de R$ 10.208 da família Reis, do contrato ORM; descontar o adiantamento de ~R$ 20 mil da NESS); o Hermes só sabia propor categoria | 2 | **A**, mas como ajuste no "a receber" que já existe, não como motor |
| "Você tem meus contatos? Nem no brain?" (o brain tem os contatos sincronizados, mas nenhuma ferramenta MCP os expõe) | 1 | lacuna nova (nenhuma de A–F) |
| "O Pix da Carla foi no dia 5 ou 6?" (não achou; inventou e depois se corrigiu quando cobrado) | 1 | qualidade da consulta, não D |
| "Por que decidi…" / histórico de decisões | 0 | **C**: confirma ADIAR |
| Correlação entre fontes | 0 | **D**: confirma ADIAR |

Também: em 22/10 às 11:49 o Hermes falou em "40 ferramentas" e citou `contatos_em_aberto`, `frentes` e `reembolsos` (catálogo de antes da ADR-023). Conferir se o catálogo dele recarregou depois da instalação. Em 13/10 errou o dia da semana.
