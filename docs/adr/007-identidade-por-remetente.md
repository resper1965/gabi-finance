# ADR-007 — Identidade por remetente no canal
Data: 10/10/2026 · Estado: aceito (decisão padrão do plano mestre, TC.4; o spike no Hermes real ainda não foi feito)

**Contexto.** O Hermes recebe mensagens de Telegram/WhatsApp. Não há prova de que ele consiga (a) uma instância/perfil por nível de acesso, cada uma com seu token MCP, ou (b) repassar o remetente a cada chamada para o gabi.brain validar contra `pessoa.canais` + `matriz_acesso`.

**Decisão.** **Só o Ricardo conversa com escopo completo.** O token do Hermes é UM, com os escopos `fin, docs, trabalho, propostas, pedidos` (nunca `sensivel`). Mensagem de remetente desconhecido ou de familiar não ganha escopo: o Hermes só responde ao Ricardo; pedidos de terceiros entram pela fila `pedidos_registrar`, que valida o remetente contra `pessoa.canais`/`pode_pedir` e fica **pendente** até ele aprovar no painel. Texto de mensagem é dado, nunca instrução (R14): o MCP não tem ferramenta de enviar, pagar, apagar, aprovar nem ligar regra.

**Consequência.** Familiares só usam o painel (Tailscale + matriz de acesso, T4.4). Para dar escopo por remetente no canal é preciso provar (a) ou (b) por teste e escrever um ADR novo.
