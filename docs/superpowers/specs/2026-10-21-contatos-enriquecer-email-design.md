# Enriquecer contatos da ness com e-mail e piso de interação para criar (design)
Data: 21/10/2026 · Estende: ADR-020 e ADR-021 · Registra: ADR-022 (a escrever na implementação)

## Objetivo
Os contatos da ness no Graph só têm nome e telefone. O Google (`contato_google_email`) já guarda e-mails ligados a telefones. O Ricardo quer que a Gabi **proponha** acrescentar esses e-mails aos contatos da ness, sempre pela fila `contato_proposta`, com o mesmo interruptor `contatos.escrita` e a mesma auditoria. Quer também uma **crítica contra contato demais**: pessoas com pouca interação não viram contato novo.

## Decisões do Ricardo (21/10)
1. Ordem: (a) e-mail do Google para contatos existentes; (c) pedir ao admin do tenant a permissão `User.ReadBasic.All` (funcionários da ness), fora do código; (b) captar remetentes de e-mail por último e só se ele pedir.
2. E-mail só **acrescenta**. Se o contato já tem e-mail diferente, deixa como está. Se o telefone tem vários e-mails no Google, propõe todos, em campos separados.
3. `adicionar_email` é a única classe aprovável em lote (só acrescenta). Qualquer outra mudança continua individual; apagar nunca entra em lote.
4. Piso de interação para **criar** contato: últimos 12 meses e (pelo menos 1 resposta do Ricardo **ou** pelo menos 5 mensagens trocadas). Sempre fora: `noreply`, listas, notificações, remetentes de sistema. Em dúvida, não cria.
5. Histórico: **só acumular**. Hoje há ~3 semanas de e-mail (`email_msg` desde 28/09) e 0 mensagens em `escuta_msg`; a janela de 12 meses enche com o tempo. Importar histórico antigo fica fora.
6. Tiago Nicastro / empresa Moqueca: o Ricardo faz no Outlook; fora do escopo.

## Mudanças
### 1. Fila: tipo `adicionar_email`
Migração 0074: o `check` de `tipo` em `contato_proposta` passa a aceitar `adicionar_email`, e entra a coluna `email_depois text` (e-mails separados por `;`, em minúsculas, sem repetição). Para `adicionar_email`, `telefone_antes` guarda o telefone E.164 do contato (chave da revalidação) e `nome_antes` o nome visto. Nova origem permitida: `google_email`. Mesma máquina de estados, mesma decisão em `decidir`, mesma auditoria.

### 2. Geração (`gabi/escuta/contatos_propostas.py`)
Para cada contato da ness, uma proposta `adicionar_email` nasce só se **todas** valem:
- o contato tem exatamente um telefone válido e esse telefone é **único** entre os contatos da ness (exclui os compartilhados que o Ricardo confirmou: escritório, família);
- esse telefone tem e-mail em `contato_google_email`;
- o nome do Google e o da ness têm pelo menos uma parte significativa em comum (token de ≥ 3 letras, sem acento e sem caixa; ignora "de", "da", "dos");
- o contato da ness **não tem** e-mail. O espelho `contato_graph` não guarda e-mail, então isso só é conferido na releitura da ponte (item 3): se o contato já tem qualquer e-mail, a gravação devolve `alterado` e a proposta vira `falhou` com motivo `contato_alterado`, sem escrever nada.

O que falha só no critério de nome ou de telefone único vai para a contagem `revisar` do resultado de `gerar` (sem proposta, sem dado de terceiros em log). Deduplicação por chave existente (`_ja_decidida`), como nos outros tipos.

### 3. Ponte (`gabi/fontes/graph_ness_contatos.py`)
Método novo `adicionar_email(gr, conta, graph_id, nome_antes, telefone_antes, emails)`:
- relê o contato (`displayName`, telefones, `emailAddresses`); só escreve se o nome e o telefone ainda conferem e `emailAddresses` está **vazio**; senão devolve `alterado`, sem escrever;
- PATCH apenas de `emailAddresses`; nenhum `DELETE`; a trava de `DELETE` continua só em `apagar`;
- wrapper em `graph_ness.py` e entrada na allowlist de `ponte.py`.

### 4. Gravação e aprovação
`contatos_gravar.py`: `_aplicar_adicionar_email` com o mesmo desenho dos outros (revalida no banco local, chama a ponte, grava `aplicada` e atualiza o espelho local). `aprovar_correcoes` passa a aceitar também `adicionar_email`, nunca `criar` nem `apagar_*`. Painel: bloco de `adicionar_email` com "aprovar todos" e lista do que será gravado (nome, telefone, e-mails).

### 5. Piso de interação para `criar` (novo módulo `gabi/escuta/interacao.py`)
`interacao(con, agora, endereco=None, telefone=None) -> {"mensagens": n, "respostas": r}` conta, nos 12 meses até `agora`:
- e-mail: `email_msg` (remetente) e `email_respondido` (respostas do Ricardo), por endereço; descarta `lista`, `noreply`/`no-reply`/`donotreply`, remetentes de sistema e classes de notificação;
- WhatsApp: `escuta_msg` por número (`de`).
Passa se `respostas >= 1` ou `mensagens >= 5`. `gerar()` só insere `criar` (hoje, remetentes aprovados do WhatsApp) quando passa. Abaixo do piso, nada entra na fila e o resultado mostra `abaixo_do_piso`. Constantes nomeadas (`JANELA_DIAS=365`, `PISO_MENSAGENS=5`, `PISO_RESPOSTAS=1`).

Com os dados de hoje quase ninguém passa; é o comportamento esperado da decisão 5.

## Segurança e consequências
- E-mail na pessoa errada é pior que e-mail faltando: por isso telefone único + nome compatível + só acrescenta. O ganho esperado é parcial (~33% dos contatos têm e-mail por telefone; parte cai fora pelos filtros).
- Depois de acrescentar e-mail, `apagar` (que recusa contato com e-mail) fica ainda mais conservador.
- Gravar e-mail no Graph é reversível só à mão no Outlook; por isso a revalidação exige `emailAddresses` vazio.
- `contatos.escrita` continua o interruptor único. Sem ele ligado, nada é gravado.
- O limite de privacidade se mantém: log só com contagens; nomes, telefones e e-mails só na fila e no painel.

## Testes (TDD)
- geração: telefone único + nome compatível gera; telefone compartilhado, nome sem token comum, e-mail já presente e telefone sem e-mail não geram; vários e-mails viram uma proposta com todos;
- ponte: escreve só `emailAddresses`; `alterado` se nome, telefone ou e-mail mudaram; sem `DELETE`;
- gravação: aplica, descarta quando o contato mudou, falha com motivo fixo quando o Graph cai;
- aprovação em lote: aceita `adicionar_email`, recusa `criar` e `apagar_*`;
- piso: 0, 1 resposta, 4 e 5 mensagens, fora da janela, `noreply`, lista; `criar` abaixo do piso não entra;
- `tests/cobrar/test_nibo.py::test_nenhuma_rota_de_exclusao_no_codigo` segue verde; suíte completa verde antes de mergear.

## Fora do escopo
Empresa, cargo, endereço; mesclar duplicados; importar histórico antigo; captar remetentes de e-mail (b); lista de funcionários (c, pedido ao admin); aprovar por Telegram.
