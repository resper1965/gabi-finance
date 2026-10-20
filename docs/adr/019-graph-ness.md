# ADR-019 · Graph da ness no gabi.brain: contatos e agenda só de leitura
Data: 19/10/2026 · Estado: aceito (código completo, nada ligado; passos do dono no runbook `#graph-ness`) · Spec: `docs/superpowers/specs/2026-10-19-graph-ness-design.md` · Plano: `docs/superpowers/plans/2026-10-19-graph-ness-base-e-agenda.md`

**Exceção (20/10/2026):** criar e corrigir contatos, só com aprovação no painel, está no ADR-020; é a única exceção ao "só leitura" dos contatos.

**Contexto.** A ness migrou para o Microsoft 365 em 19/10 e o Ricardo pediu agenda, e-mail, contatos e Teams da `resper@ness.com.br`. O cliente Graph antigo (`graph.py`, IONIC) usa certificado e nunca foi validado; o app `ness-automacao` já existia com secret.

**Decisões e razões.**
1. **Secret em vez de certificado para a ness** (client credentials): é o que o app tem e o teste real passou; o certificado fica para a IONIC. Cliente novo e separado (`graph_ness.py`), sem mexer no `graph.py`.
2. **Mesmo molde do Google:** ponte própria `graph_ness` (lista branca de métodos) no serviço de fontes, único com rede e segredo; a agenda reaproveita o motor (`ResultadoEventos`, `sincronizar` escolhe o cliente pelo `provedor`) e os contatos o roteador de conta.
3. **Só leitura e só a caixa da ness.** O app tem permissão no tenant inteiro; a trava é o código (conta vem de `M365_CONTAS`, `GET` apenas, teste varre o módulo) e, fora dele, a política de acesso do Exchange. Risco aceito: até a política existir, a barreira é o código.
4. **`deltaLink` do banco só vai ao host do Graph.** Sem isso um valor adulterado em `agenda_fonte.sync_token` levaria o Bearer do app para fora.
5. **E-mail da ness (19/10, mesmo molde do ADR-018):** provedor `graph` no correio, sobre `mailFolders/inbox/messages/delta`. Única escrita: `move` para `deleteditems`/`inbox` (destino fixo, `Prefer: IdType="ImmutableId"` para o id sobreviver à mudança de pasta). Nunca envia, responde, encaminha nem apaga de vez; corpo da mensagem nunca é lido. Risco aceito: `Mail.ReadWrite` é mais amplo que a lixeira; a garantia é a lista branca da ponte + teste de varredura (e a política do Exchange, quando existir).
6. **Fora desta fase:** Teams (sem guardar texto), com plano próprio (superado pelo item 7).

## Teams (20/10/2026)
7. **Só metadados, sem texto e sem modelo na fase 1.** O Teams da ness é lido pela ponte `graph_ness` (`teams_chats`, `teams_mensagens`) apenas para saber quem escreveu, quando e se houve resposta; o conteúdo das mensagens não é guardado nem enviado a modelo. Mesma trava do restante: só leitura e só a conta cadastrada (a permissão `Chat.Read.All` alcança o tenant, a restrição é o código).
8. **Fora desta fase:** responder (exigiria exceção à R2 em ADR próprio), canais, modelo (fase 2) e a ionic. A ionic pode ter o acesso mais restrito pelo administrador; o acesso delegado `Chat.Read` é a alternativa, não implementada.
