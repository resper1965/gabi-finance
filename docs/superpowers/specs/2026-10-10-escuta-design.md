# Escuta do WhatsApp pessoal no gabi.brain — design

Data: 10/10/2026 · Estado: **rascunho para revisão do Ricardo** · Substitui o agente `escuta` do OpenClaw (workspace-escuta, `escuta.py`).

## 1. Intenção (o que o Ricardo pediu)
- Ficar só com **Hermes + gabi.brain**. O agente `escuta` do OpenClaw não pode se perder: **mantém**, e vira **timer do brain** (código fixo, sem agente).
- A escuta continua **nunca respondendo a ninguém**. Faz só três coisas: registrar **pedido de dinheiro**, **documento de saúde** (reembolso do plano) e **crise**.
- **Crise: só chamar atenção**, para o Ricardo e mais ninguém. Sem citar a mensagem, sem avaliação, sem conselho.
- Quem pode gerar registro é uma **lista de aprovados**, que o Ricardo mantém **pelo painel, sem código**.
- **Contatos do Google** dão nome aos números e alimentam a fila de aprovação. Só sugerem; nunca aprovam.
- Fora deste spec: agenda do Google (sub-projeto seguinte, reabre só a agenda da Fase 3), o corte do `gabi-financeiro` (G21), Telegram/WhatsApp do Hermes (Tasks 12–13), desligar o OpenClaw (Task 15).

## 2. Regras herdadas (valem sem exceção)
R1 a Gabi sugere, o Ricardo decide · R2 nenhum envio externo automático (a escuta **não envia nada ao remetente**; só avisa o Ricardo) · R14 texto de terceiros é dado delimitado, nunca instrução · ADR-007 só o Ricardo conversa com o Hermes · ADR-014 saúde não fica no `gabi.db` · dados nunca chumbados no código · segredos o Ricardo coloca.

## 3. Arquitetura
```
WhatsApp pessoal ─► ouvinte (serviço leve, só lê) ─► escuta_msg (caixa de entrada, estado "nova")
                                                            │
        timer gabi-brain-escuta (5 min) ◄───────────────────┘
          1. resolve remetente  ─► aprovado? ─ não ─► escuta_remetente (fila "Novos remetentes"), texto retido sem modelo
          2. aprovado ─► classificar (modelo barato, 1 chamada por msg, sem ferramentas) ─► JSON validado
          3. grava: pedido (Cobrar) | pista de saúde (fila do reembolso) | aviso de crise | nada (apaga o texto)
```

### 3.1 Ouvinte (`escuta-ouvinte`, serviço próprio)
- Aparelho vinculado ao número pessoal (Baileys), **somente leitura**: não tem código de envio. Pareamento por QR é passo do Ricardo.
- Para cada mensagem recebida: grava `escuta_msg(id_externo, de, grupo, recebida_em, texto, anexo_caminho)`. Idempotente por `id_externo`.
- Grupos: gravados com `grupo=1` e **ignorados** no processamento, a menos que o grupo esteja aprovado.
- Falha do ouvinte não derruba o brain (o timer só processa o que existe). O vigia avisa se o ouvinte ficar sem receber nada por tempo anormal.
- Gatilho de crise: uma lista curta de palavras de risco, **vinda de cadastro** (não do código), roda no ouvinte e dispara o timer na hora. É só um acelerador; a decisão continua sendo do brain.

### 3.2 Lista de aprovados (sem código)
- Fica em `pessoa` (já tem `canais` e `pode_pedir`). Nova marca `escuta_aprovada` e `papel` (família, prestador, cobrança). Grupos aprovados em `escuta_grupo`.
- Quem já tem `whatsapp:` cadastrado entra como **candidato**; o Ricardo revisa a lista uma vez no painel antes de ligar a escuta (nada entra aprovado sozinho).
- **Fila "Novos remetentes"** (painel, em Cadastros): nome (via contatos, se houver), número, quantidade de mensagens. Botões: **Aprovar** (pede o papel na hora), **Ignorar**, **Bloquear**.
- Remetente novo gera um `aviso` Telegram curto: "Novo remetente: <nome/número>. Aprovar no painel". Sem texto da mensagem.
- Mensagens retidas de quem estava na fila: ao **aprovar**, são processadas; ao **ignorar**, apagadas; **bloqueado** nunca mais é gravado.
- Remetente fora da lista **nunca chama o modelo**. Única exceção: palavra de risco clara → aviso de atenção, sem citar a mensagem.

### 3.3 Classificação
- Entrada: texto da mensagem (e, para PDF, o texto extraído) entre marcas de dado (R14), CPF mascarado (`gabi.mascara`), sem nome de remetente além do papel.
- Saída esperada: `{"tipo": "pedido"|"saude"|"crise"|"nada", "confianca": 0..1, "campos": {...}}`. Campos por tipo seguem o `escuta.py` atual (pedido: favorecido, valor, forma, chave_ou_linha, vence, motivo; saúde: caso, documento, paciente, prestador, data, valor, doc_prestador, conselho, especialidade).
- O código **valida** o JSON (tipo permitido, tamanhos, valor numérico, data válida); resposta inválida vira "nada" + contagem de falha, nunca entrada livre.
- Modelo e teto: o mesmo padrão de `gabi/dinheiro/modelo.py` (cliente injetado, teto diário e mensal, alerta aos 70%, entra no vigia de custo). Modelo rápido por padrão; confiança < 0,7 repete com o modelo forte.
- **Crise** não depende da confiança: na dúvida, avisa.

### 3.4 Destinos
- **pedido** → `gabi/cobrar/pedidos.py` (já registra sem dizer que pagou; só o Ricardo aprova no painel). O remetente aprovado tem que ter `pode_pedir`.
- **saúde** → o anexo vai para o `consume` do Paperless (assume o papel do `gabi-wa-docs`) e a pista segue o fluxo existente do `reembolso_fila.py` (casa por checksum, classifica, avisa). O texto de saúde **não** fica em `escuta_msg`: é apagado depois de extrair os campos; os dados de saúde seguem o caminho que já existe (Paperless/reembolso), sem ampliar o que o `gabi.db` guarda hoje.
- **crise** → um `aviso` Telegram ao Ricardo: "Possível crise: <nome ou número>. Abra a conversa." Nada mais. Sem nível, sem trecho, sem conselho. Só ao Ricardo.
- **nada** → texto e anexo apagados; fica só `id_externo`, remetente, data e tipo.

### 3.5 Contatos do Google
- Acesso `contacts.readonly` no mesmo OAuth do G12 (acrescenta um escopo). **Contas**: as mesmas da agenda (parâmetro de cadastro; decisão final do Ricardo, padrão = ness, bekaa.eu, esper.ws).
- Timer diário, sem modelo, grava `contato_google(conta, nome, telefone_e164)`. Só nome e telefone; nada de foto, e-mail, endereço ou nota.
- Uso: dar nome ao número na fila e no aviso; botão "Trazer dos contatos" no painel (seleção pessoa a pessoa) cria `pessoa`. **Estar nos contatos não aprova ninguém.**
- Revogar o acesso apaga a tabela.

### 3.6 Aposentadoria do que sai
- `reembolso_fila.py` e `reembolso_segunda` entram no brain sem mudar a lógica (portados com os testes).
- `gabi-wa-docs`, o agente `escuta`, `escuta.py` e `gabi-reembolso.path` saem **depois** do paralelo (seção 6).
- Filas históricas (`feitas/`, `falhas/`) não se apagam; são arquivadas.

## 4. Dados (migração 0021)
`escuta_msg`, `escuta_remetente` (estado: pendente/aprovado/ignorado/bloqueado), `escuta_grupo`, `contato_google`; colunas `pessoa.escuta_aprovada` e `pessoa.papel_escuta`. Parâmetros de cadastro: palavras de risco, contas de contatos, teto de custo, horas sem receber. Nada disso no código.

## 5. Erros e segurança
- Sem chave do modelo ou teto estourado: o timer **não classifica**; mensagens ficam "novas" e um aviso diz isso. Crise por palavra de risco continua funcionando sem modelo.
- Conteúdo de terceiros nunca é instrução; o modelo não tem ferramentas, só devolve JSON.
- O ouvinte não tem permissão de escrita no WhatsApp nem credencial do brain além de inserir na caixa.
- Logs não carregam texto de mensagem.

## 6. Testes e aceite
- Unidade (contra cliente de modelo falso): classificação de cada tipo; JSON inválido; injeção ("ignore as instruções…") vira "nada"; remetente fora da lista não chama o modelo; crise sem modelo; grupo ignorado; texto de "nada" apagado; saúde não deixa texto no banco.
- Painel: fila, aprovar/ignorar/bloquear, "Trazer dos contatos" (vitest).
- Ouvinte: contra servidor falso do WhatsApp.
- **Paralelo** (aceite): ouvinte e brain rodam ao lado do agente antigo por alguns dias, só em modo registro; compara-se o que cada um classificou. Só depois a escuta antiga é aposentada. Aceite com dado real, como nas demais fases.

## 7. Pendências do Ricardo (não bloqueiam o código)
Parear o ouvinte (QR) · G12 com o escopo de contatos · revisar a lista de candidatos no painel · confirmar as contas de contatos · chave do modelo já existe (OpenRouter).
