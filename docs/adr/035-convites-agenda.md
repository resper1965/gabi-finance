# ADR-035 · Convites de agenda recebidos: aviso, conflito e resposta com o seu clique

Data: 04/11/2026 · Estado: aceito (implementado na branch `feat/convites-agenda`, aguarda autorização de merge e instalação) · Spec: `docs/superpowers/specs/2026-11-04-convites-agenda-design.md` · Plano: `docs/superpowers/plans/2026-11-04-convites-agenda.md` · Amplia o ADR-024

**Contexto.** O ADR-024 deixou o Hermes marcar evento e responder no Teams, sempre com o seu clique em **Enviar**. Faltava o convite que chega de outras pessoas: o Outlook da ness recebe e você só vê quando abre a agenda. Agora o brain avisa, mostra se bate com outro compromisso e propõe a resposta.

**Decisões.**
1. **R2 mantida:** nada é respondido sozinho. O Hermes (ou o painel) só PROPÕE aceitar, talvez ou recusar; a resposta só sai no clique em **Enviar**, uma tentativa, como nos outros envios.
2. **Só a ness (Graph).** Google, comentário na resposta, sugerir outro horário e botão no Telegram ficam fora.
3. **Convite pendente** = evento recebido (não organizado por você), futuro, que não é de dia inteiro e ainda sem resposta. Convite que você organiza nunca vira aviso nem proposta.
4. **Conflito** é calculado na leitura (não é gravado): outro evento no mesmo intervalo. Evento "livre" ou de dia inteiro não conta; encostar (fim = início) também não.
5. **Aviso** novo `convite_agenda` no Telegram, com os conflitos no texto. Mudou o horário do convite: avisa de novo; mesmo horário nunca repete.
6. **Proposta** `convite_resposta` (migração 0088 recria `envio_proposta` com o tipo novo). Duas abertas para o mesmo convite (pendente ou enviando) não existem; depois de falhar ou vencer pode propor de novo.
7. **Ferramenta MCP** `propor_resposta_convite` (escopo `envios`; 71 ferramentas no include) e duas rotas em `/api/v1/envios/convites`; no painel, um bloco "Convites" em Envios.

**Divergências da spec, como ficaram.**
1. **Token:** a spec dizia "conta delegada"; a agenda da ness já é escrita com o token de aplicativo (`Calendars.ReadWrite`, como `evento_criar`). As três chamadas (`accept`, `tentativelyAccept`, `decline`) usam o mesmo token. Nenhum login novo.
2. **Idempotência:** essas chamadas não aceitam `transactionId`. Vale a regra de sempre: uma tentativa só; erro 5xx vira `incerto` e nunca repete. Responder duas vezes é inofensivo.
3. **"Obsoleta":** `envio_proposta.estado` não tem esse valor. 404 ou 409 do Graph viram `falhou` com `motivo='convite_obsoleto'`, sem repetir; a conferência local no clique (abaixo) usa o mesmo código. Série não encontrada cai no mesmo código.
4. **Resposta 202 sem corpo:** o cliente do Graph tratava corpo vazio como "resposta inválida"; agora é sucesso para essas chamadas.
5. **`declined` nunca fica gravado:** a sincronização já apaga o evento recusado; o valor existe só no mapeamento.

**Pontos decididos.**
- **Provedor gravado** = o da `agenda_fonte` da conta. Uma conta Google em `envios.contas_agenda` falharia fechada no envio (`fonte_indisponivel`). Hoje `contas_agenda` tem só a conta Graph da ness.
- **Convite já respondido:** o Graph pode devolver 400 em vez de 404/409. Nesse caso aparece `falhou` com `provedor_400`: sem erro 500 e sem repetir. A confirmar no seu teste real.
- **Conferência local no clique, antes do Graph:** se o organizador remarca, o Graph mantém o mesmo id e não devolve 404/409; responder de novo um convite já respondido também passa. Por isso, no **Enviar**, o brain relê o evento na agenda local: se sumiu, já não está sem resposta (você respondeu no Outlook) ou o início/fim mudou, a proposta vira `falhou` com `convite_obsoleto` sem nenhuma chamada ao Graph (falha fechada). Basta propor de novo com o horário atual.

**Consequências.** O Hermes precisa da ferramenta nova no include e do SOUL com a linha do convite (passos do runbook `#envios`). Enquanto `envios.escrita` não estiver ligado, **Enviar** responde 409 e nada sai.

**Fora.** Responder com comentário, propor outro horário, convites do Google, botões no Telegram, resposta automática.

**Desfazer.** Backup `gabi.db.antes-convites-<data>`; `git revert` do merge e `sudo ~/instalar-brain.sh`. A migração 0088 traz o SQL de desfazer no cabeçalho. Tirar `propor_resposta_convite` do include do Hermes e `sudo systemctl restart hermes-gateway`.
