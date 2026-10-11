# Escuta do WhatsApp pessoal no gabi.brain — design

Data: 10/10/2026 · Estado: **rascunho para revisão do Ricardo** · Substitui o agente `escuta` do OpenClaw (workspace-escuta, `escuta.py`).

## 1. Intenção (o que o Ricardo pediu)
- Ficar só com **Hermes + gabi.brain**. O agente `escuta` do OpenClaw não pode se perder: **mantém**, e vira **timer do brain** (código fixo, sem agente).
- A escuta continua **nunca respondendo a ninguém**. Faz só três coisas: registrar **pedido de dinheiro**, **documento de saúde** (reembolso do plano) e **crise**.
- **Crise: só chamar atenção**, para o Ricardo e mais ninguém. Sem citar a mensagem, sem avaliação, sem conselho.
- Quem pode gerar registro é uma **lista de aprovados**, que o Ricardo mantém **pelo painel, sem código**.
- **Contatos do Google** dão nome aos números e alimentam a fila de aprovação. Só sugerem; nunca aprovam. Hoje em `resper@ness.com.br` e `resper@gmail.com`; **meta: tudo no `resper@gmail.com`** (a ness migra para a Microsoft).
- **Dados de saúde são reprocessáveis**, sempre (decisão do Ricardo, muito importante), em especial a lista que ele está copiando. Nada de saúde é apagado depois de classificado.
- Fora deste spec: agenda do Google (sub-projeto seguinte, reabre só a agenda da Fase 3), o corte do `gabi-financeiro` (G21), Telegram/WhatsApp do Hermes (Tasks 12–13), desligar o OpenClaw (Task 15).

## 2. Regras herdadas (valem sem exceção)
R1 a Gabi sugere, o Ricardo decide · R2 nenhum envio externo automático (a escuta **não envia nada ao remetente**; só avisa o Ricardo) · R14 texto de terceiros é dado delimitado, nunca instrução · ADR-007 só o Ricardo conversa com o Hermes · ADR-014 saúde não fica no `gabi.db`: fica no arquivo cifrado próprio (AES-256-GCM) · dados nunca chumbados no código · segredos o Ricardo coloca.

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
- Para cada mensagem recebida: grava `escuta_msg(id_externo, de, grupo, recebida_em, texto, anexo_caminho)`. Idempotente por `id_externo`. `recebida_em` do spool: com offset é convertido; sem offset vale Brasília; gravado em UTC.
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
- **saúde** → o **anexo vai para o Paperless** (`consume`, com a etiqueta `gabi:saude-exame`; assume o papel do `gabi-wa-docs`) e **o Paperless é o arquivo do original**. A extração, a confirmação do dono, o histórico por familiar e o **reprocessamento** são do módulo de exames (spec 2026-10-11-exames-design). A pista de reembolso segue o fluxo do `reembolso_fila.py` (casa por checksum, classifica, avisa). Mensagem de saúde **só de texto** (sem anexo) é guardada no cofre cifrado (ADR-014), nunca em `escuta_msg` nem no `gabi.db`. Nada de saúde é apagado.
  - **Nota de desvio (11/10/2026, ADR-016):** a implementação NÃO guarda a saúde só de texto no cofre (o cofre é do projeto dos exames): gera o aviso `escuta_saude` (só número e nome) e apaga o texto; o original continua no WhatsApp do Ricardo. Limitação conhecida, aceita como gate da troca para `ativo`.
- **crise** → um `aviso` Telegram ao Ricardo: "Possível crise: <nome ou número>. Abra a conversa." Nada mais. Sem nível, sem trecho, sem conselho. Só ao Ricardo.
- **nada** → texto e anexo apagados (vale só para tipo "nada"; saúde, pedido e crise nunca são apagados daqui); fica só `id_externo`, remetente, data e tipo.

### 3.5 Contatos do Google (duas contas hoje, uma só no futuro)
- **Hoje** os contatos estão em `resper@ness.com.br` **e** em `resper@gmail.com`. **Meta do Ricardo: tudo em `resper@gmail.com`**, porque a ness migra para a Microsoft em breve.
- Acesso `contacts.readonly` no OAuth do G12 (acrescenta um escopo), **somente leitura**, para as duas contas. As contas são parâmetro de cadastro: quando a ness sair do Google, basta tirá-la da lista, sem código.
- Timer diário, sem modelo, grava `contato_google(conta, nome, telefone_e164)`. Só nome e telefone; nada de foto, e-mail, endereço ou nota. O mesmo telefone nas duas contas vira **um** contato (união por telefone normalizado); se os nomes diferem, vale o do Gmail.
- **Consolidar no Gmail:** o brain **não escreve** nos contatos do Google (continua só leitura). Ele gera, pelo painel, um arquivo (CSV do Google) com os contatos que **existem só na ness**, para o Ricardo importar no Gmail em contacts.google.com. Depois da importação, o relatório "só na ness" fica vazio e a ness pode ser removida da lista de contas.
- **Prazo:** a leitura da ness só funciona enquanto ela estiver no Google. O passo de exportação deve ser feito **antes** da migração para a Microsoft.
- Uso: dar nome ao número na fila e no aviso; botão "Trazer dos contatos" (seleção pessoa a pessoa) cria `pessoa`. **Estar nos contatos não aprova ninguém.**
- Revogar o acesso apaga a tabela.

### 3.6 Aposentadoria do que sai
- `reembolso_fila.py` e `reembolso_segunda` entram no brain sem mudar a lógica (portados com os testes). **Nota de desvio (11/10/2026, ADR-016):** o porte não foi feito; fica como item aberto em `docs/PLANO-DEFINITIVO.md`, e `gabi-reembolso*` sai da lista de aposentadoria da escuta até lá.
- `gabi-wa-docs`, o agente `escuta` e `escuta.py` saem **depois** do paralelo (seção 6); `gabi-reembolso.path` só depois do porte do reembolso (ver nota acima).
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
- Saúde: item entra no cofre cifrado e nada de saúde aparece no `gabi.db` (teste varre o banco); reprocessar gera versão nova e preserva a anterior; reprocessar em lote; sem acesso total, o painel nega; importação da lista por arquivo.
- Painel: fila, aprovar/ignorar/bloquear, "Trazer dos contatos" (vitest).
- Ouvinte: contra servidor falso do WhatsApp.
- **Paralelo** (aceite): ouvinte e brain rodam ao lado do agente antigo por alguns dias, só em modo registro; compara-se o que cada um classificou. Só depois a escuta antiga é aposentada. Aceite com dado real, como nas demais fases.

## 7. Pendências do Ricardo (não bloqueiam o código)
Parear o ouvinte (QR) · G12 com o escopo de contatos (as duas contas) · importar no Gmail o arquivo "só na ness" antes da migração · revisar a lista de candidatos no painel · chave do modelo já existe (OpenRouter) · chave do cofre de saúde (a mesma do ADR-014, já é dele).

**Saúde:** a lista do Ricardo são PDFs de exames; o histórico por familiar é o módulo de exames (spec 2026-10-11-exames-design). Aqui a escuta só leva o anexo ao Paperless.

**Nota para o sub-projeto da agenda:** a ness.com.br migra para a Microsoft; a agenda dela passa a depender do G11 (Graph), não do Google. A agenda do Gmail pessoal segue pelo Google.
