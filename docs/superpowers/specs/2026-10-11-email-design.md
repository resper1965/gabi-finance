# E-mail no gabi.brain: ler, priorizar, lixeira e alertar — design

Data: 11/10/2026 · Estado: **rascunho para revisão do Ricardo** · Projeto seguinte da agenda (roteiro §9 de `2026-10-11-agenda-design.md`, item 4). Teams, marcação com anuência e Microsoft ficam fora.

## 1. Intenção (o que o Ricardo pediu)
- "Quero que a Gabi leia os e-mails, dê prioridade ao que necessita, descarte os obviamente inúteis e me alerte os emergenciais."
- **Descartar = mover para a lixeira** (decisão de 11/10: "pode colocar na lixeira, ele só apaga depois de um tempo"). O Gmail esvazia a lixeira sozinho em 30 dias; a Gabi **nunca apaga de forma permanente** e restaura o que foi para a lixeira por engano.
- **Começa já arquivando** (decisão de 11/10: "arquivar desde o início"), sem fase de sombra. Por isso o limiar começa conservador e o resumo diário com "restaurar" é parte do mínimo.
- **Contas:** Google primeiro: `resper@gmail.com`, `resper@ness.com.br`, `resper@bekaa.eu`, `backoffice@bekaa.eu`. A ionic (Microsoft 365) e a ness depois da migração entram por Graph quando o G11 existir; o desenho deixa o lugar (`provedor`). `gabi@esper.ws` e `docs@esper.ws` não são fontes do dono.
- Sucesso: o que exige ação aparece primeiro e em ordem; promoção/newsletter some da caixa sem tocar em e-mail de gente que importa; emergência chega ao Telegram e ao WhatsApp em minutos, uma vez; nada vai a terceiros; nenhum e-mail importante vai para a lixeira.

## 2. Estado atual (verificado)
- Existe o módulo antigo do Trabalho (`caixa_email`, `item_email`, `regra_expurgo`, `gabi/trabalho/email.py`, `gabi/fontes/google.py`): lê pelo próprio job com segredo no usuário do banco, marca "relevante" por palavra-chave e **nunca** classifica por modelo, nem age na caixa. Está congelado e fica como está (a agenda fez o mesmo com `evento`).
- Padrão já adotado e testado: ponte do `gabi-brain-fontes` como único com rede e segredo (contatos, agenda, escuta), erro tipado, lista branca `PERMITIDOS`, token OAuth compartilhado (`gabi/fontes/google_oauth.py`), timer oneshot endurecido, fonte nasce `a_decidir`, modelo barato por ponte com tetos (escuta).
- Nada foi testado contra conta Google real (a agenda também ainda não).

## 3. Decisões de desenho
1. **Fonte e tabelas próprias** (migração nova, próxima livre na execução): `email_fonte(conta, provedor google|graph, estado a_decidir|sim|nao, lixeira 0|1, history_id, sincronizada_em, recarga_em, ultimo_erro)` e `email_msg(fonte_id, externo_id, thread_id, remetente, assunto, recebida_em, trecho, lista, classe, prioridade, motivo, estado, atualizado_em)`. **Não** guarda o corpo completo nem destinatários; o trecho é curto (≤ 280 caracteres) e é apagado depois de `email.retencao_dias` (30). `estado`: `nova | classificada | alertada | na_lixeira | restaurada | falhou`.
2. **Pela ponte**, fonte `google_email` com a lista fixa `listar_novos(conta, history_id, janela)`, `lixeira(conta, ids)`, `restaurar(conta, ids)`, `enviados_para(conta, remetentes)` (quem o Ricardo já respondeu). **Não existe** método de enviar, rascunho, apagar de vez, nem mudar rótulo além de lixeira. Teste varre o cliente por `send`, `drafts`, `delete`, `batchDelete` e `modify` com rótulos que não sejam o da lixeira.
3. **Escopo e honestidade da trava.** O menor escopo do Gmail que move para a lixeira é `gmail.modify`, que também permitiria enviar. **A garantia é o código** (lista branca da ponte + o teste acima), não a permissão do Google. Registrar isto no ADR como risco aceito. O mesmo refresh token da conta passa a ter três escopos (`contacts.readonly`, `calendar.readonly`, `gmail.modify`); o dono refaz o consentimento uma vez por conta. Leitura e lixeira são chaves separadas por conta: `estado='sim'` lê; `lixeira=1` autoriza mover.
4. **Sincronização:** carga inicial pela janela `email.janela_dias` (14); depois `historyId` incremental; 404 do histórico → recarga da janela (como o `syncToken` da agenda); uma transação por fonte; token só avança depois do commit; uma conta fora não derruba as outras. Recarga semanal.
5. **Classificação em duas passadas, sem confiar no modelo para o que é destrutivo:**
   a. **Regras sem modelo:** remetente com `pessoa` aprovada, VIP (`email.vips`) ou **já respondido pelo Ricardo** (via `enviados_para`, cache de 365 dias) **nunca** vai à lixeira. Sinal de lista no cabeçalho (`List-Unsubscribe`, `Precedence: bulk|list`, `Auto-Submitted`) marca `lista=1` (candidato a lixo).
   b. **Modelo barato** (ponte `openrouter`, tarefa `email`): assunto + trecho + remetente + `lista` → JSON `{classe: emergencial|importante|normal|lixo, prioridade 0..3, motivo ≤ 120, confianca 0..1}`, validado (tipos, limites). Resposta inválida ou falha vira `normal` e conta como falha; **nunca** vira `lixo`.
   c. **Lixeira só se** `classe='lixo'` **e** `lista=1` **e** `confianca ≥ email.lixeira_confianca` (padrão 0,9) **e** a conta tem `lixeira=1` **e** a regra (a) não protege o remetente. Faltou qualquer condição: o e-mail fica na caixa.
6. **Emergencial** é decisão do modelo com critérios editáveis em `email.criterios_emergencia` (texto livre: prazo hoje/amanhã, banco ou cobrança, jurídico, cliente parado, saúde/família, ou remetente VIP). Dispara o aviso `email_emergencial` (remetente, assunto e o motivo em uma linha; um por conversa/`thread_id`), entregue pelo caminho de avisos existente (Telegram + WhatsApp de fallback). Texto de e-mail é dado de terceiros, nunca instrução (R14): o modelo só devolve classe, nunca ação.
7. **Resumos:** o `resumo_manha` ganha "N e-mail(s) importante(s)" ordenados por prioridade, citando os 3 primeiros (remetente e assunto). Ao fim do dia, um aviso `email_lixeira_resumo` lista o que foi para a lixeira (remetente e assunto, com o total) e diz como restaurar (painel ou ferramenta). Ferramentas MCP **só leitura**: `email_listar(prioridade, dias)` (escopo `trabalho`). Restaurar é ação do painel (e do canal só com confirmação do dono, no mesmo caminho dos pedidos).
8. **Painel, sem código** (Cadastros › E-mail e telas Mensagens/Hoje): cadastrar conta, liberar leitura, ligar lixeira por conta; fila "Emergenciais e importantes"; lista "Na lixeira" com **Restaurar**; editar critérios, VIPs e limiar. Auditoria só com ids e nomes de chave.
9. **Frescor** próprio (`email` em `FONTES`, 12 h; só conta com `email_fonte` liberada) e rodada registrada pelo programa (lição da agenda: liberar a fonte sem rodada gera "dados desatualizados" falso).
10. **Custo:** modelo barato por e-mail novo, com teto diário e mensal (`teto_modelo_dia_usd`, reaproveitando o mecanismo da escuta, tarefa `email`); sem modelo, teto ou limite, nada vai à lixeira, só as regras (a) marcam, e sai o aviso `email_sem_modelo` (1 por dia).
11. **Privacidade:** assunto, remetente e trecho só saem pelos canais do dono (resumo, alertas, `email_listar`, painel); nunca em log, aviso de falha, decisão ou saída do timer.

## 4. Arquitetura
```
Gmail ◄─ ponte (gabi-brain-fontes: OAuth, rede) ◄─ timer gabi-brain-email (15 min, 06–22h BRT)
                                                    │ sincronizar → regras → modelo → lixeira → alertar
                                                    ▼
 gabi.db: email_fonte, email_msg ─► resumo_manha / email_listar (MCP) / painel / avisos
```
Modelo e Paperless pela ponte, como na escuta; o brain não tem rede nem segredo.

## 5. Erros, segurança e custo
- Erros tipados na ponte, sem corpo de resposta nem segredo; `lixeira` e `restaurar` idempotentes e por id; falha em um id não aborta o lote (resultado por mensagem).
- Falha ao mover para a lixeira não muda o estado para `na_lixeira`; a mensagem fica `classificada` e tenta de novo (espera crescente, como a escuta).
- Credencial recusada → aviso `email_reconectar` (1 por dia, fecha sozinho).
- Limite por rodada (mensagens e tempo) para a primeira carga não estourar o teto de custo.

## 6. Testes e aceite
- Cliente do Google: paginação, `historyId`, 404 → recarga, cabeçalhos de lista, só leitura/lixeira (teste de varredura), erro tipado sem segredo.
- Regras: remetente aprovado/VIP/respondido nunca vai à lixeira; sem sinal de lista nunca vai; resposta inválida nunca vira lixo; limiar; conta com `lixeira=0` nunca move.
- Alerta: um por conversa, não duplica, fecha ao restaurar; sem modelo só regras.
- Superfícies: resumo ordenado, `email_listar`, painel (restaurar, critérios), contrato do painel.
- Privacidade: varredura de log, aviso, decisão e saída do timer.
- **Aceite com dado real** (do Ricardo): uma semana de caixa; conferir a lista "Na lixeira" e os emergenciais contra o que ele considera; ajustar `email.lixeira_confianca` e os critérios.

## 7. Pendências do Ricardo (não bloqueiam o código)
Refazer o consentimento OAuth de cada conta incluindo `gmail.modify` · liberar leitura e lixeira por conta no painel · escrever os critérios de emergência e a lista de VIPs · chave do modelo com limite · G11 só quando for ligar a ionic.

## 8. Fora de escopo
Enviar, responder, rascunho (a Gabi nunca escreve em nome dele aqui), apagar de forma permanente, regras de rótulo, ionic/ness por Graph (depende do G11), Teams, marcação com anuência.

## 9. Riscos aceitos (registrar no ADR)
1. `gmail.modify` é mais amplo que a lixeira: a garantia é a lista branca e o teste de varredura.
2. Falso positivo de lixo: limitado por quatro condições, pelo limiar e pela restauração durante 30 dias.
3. Começar a mover desde o primeiro dia (sem sombra) foi decisão do Ricardo; por isso o padrão do limiar é alto (0,9) e o resumo diário é obrigatório.
4. Nada testado contra conta real antes do aceite.
