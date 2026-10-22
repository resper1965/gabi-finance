# ADR-024 · Envios com anuência: marcar agenda e escrever no Teams (exceção à R2)

Data: 22/10/2026 · Estado: aceito (branch `feat/envios-anuencia`; nada ligado até os passos do dono) · Spec: `docs/superpowers/specs/2026-10-22-envios-anuencia-design.md` · Plano: `docs/superpowers/plans/2026-10-22-envios-anuencia.md` · Item: AT1

**Contexto.** A R2 proíbe envio externo automático. Em 22/10 o Ricardo pediu que o brain marque reunião com convidados (ness, bekaa e gmail) e escreva no Teams da ness, em chat existente ou em canal de equipe, sempre com a anuência dele em cada envio.

**Decisões.**
1. **Só o Ricardo inicia, pelo Hermes.** As ferramentas `propor_evento` e `propor_teams` (escopo `envios`) só gravam uma proposta em `envio_proposta`. Nenhuma ferramenta MCP aprova ou envia.
2. **O "sim" é dado no painel, um clique por envio.** A rota manda junto o hash do conteúdo exibido; o conteúdo não muda depois de criado; a proposta vence em 24h ou no início do evento. O modelo fica fora da aprovação.
3. **Uma tentativa só.** A passagem `pendente → enviando` é atômica e a chave de idempotência vai ao provedor (id do evento no Google, `transactionId` no Graph). Timeout vira `incerto` e nunca é repetido sozinho.
4. **Interruptor `envios.escrita`**, desligado por padrão, e lista de contas `envios.contas_agenda` em `parametro`. Teams só nas contas `teams_fonte='sim'` da `M365_CONTAS`.
5. **Teams com login delegado** do Ricardo (código de dispositivo; refresh token no env do serviço de fontes, colocado por ele; rotação só em memória). Escrita só em `graph_ness_envios.py`, com varredura própria; `graph_ness.py` continua sem enviar.
6. **Nada de conteúdo em log ou auditoria**: só id, tipo, conta e estado.

**Consequências e riscos aceitos.**
- `Calendars.ReadWrite` de aplicativo alcança o tenant da ness inteiro; a barreira é o código (`M365_CONTAS` + `envios.contas_agenda`). O mesmo modelo da ADR-020: os métodos da ponte não conferem aprovação, e as travas ficam na rota.
- O token delegado do Teams expira até 90 dias depois do login (o rotacionado não é persistido para não gravar segredo pelo código). Expirado, o envio falha com `login_teams_expirado` e o Ricardo refaz o login.
- O convite da agenda sai por e-mail aos convidados: é envio externo, coberto pelo clique.

**Fora desta fase.** Remarcar, cancelar ou responder convite; conversa nova no Teams; ionic; backoffice@bekaa.eu; sugestão de envio pelo brain; aprovação por chat ou Telegram; e-mail.
