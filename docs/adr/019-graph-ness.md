# ADR-019 · Graph da ness no gabi.brain: contatos e agenda só de leitura
Data: 19/10/2026 · Estado: aceito (código completo, nada ligado; passos do dono no runbook `#graph-ness`) · Spec: `docs/superpowers/specs/2026-10-19-graph-ness-design.md` · Plano: `docs/superpowers/plans/2026-10-19-graph-ness-base-e-agenda.md`

**Contexto.** A ness migrou para o Microsoft 365 em 19/10 e o Ricardo pediu agenda, e-mail, contatos e Teams da `resper@ness.com.br`. O cliente Graph antigo (`graph.py`, IONIC) usa certificado e nunca foi validado; o app `ness-automacao` já existia com secret.

**Decisões e razões.**
1. **Secret em vez de certificado para a ness** (client credentials): é o que o app tem e o teste real passou; o certificado fica para a IONIC. Cliente novo e separado (`graph_ness.py`), sem mexer no `graph.py`.
2. **Mesmo molde do Google:** ponte própria `graph_ness` (lista branca de métodos) no serviço de fontes, único com rede e segredo; a agenda reaproveita o motor (`ResultadoEventos`, `sincronizar` escolhe o cliente pelo `provedor`) e os contatos o roteador de conta.
3. **Só leitura e só a caixa da ness.** O app tem permissão no tenant inteiro; a trava é o código (conta vem de `M365_CONTAS`, `GET` apenas, teste varre o módulo) e, fora dele, a política de acesso do Exchange. Risco aceito: até a política existir, a barreira é o código.
4. **`deltaLink` do banco só vai ao host do Graph.** Sem isso um valor adulterado em `agenda_fonte.sync_token` levaria o Bearer do app para fora.
5. **Fora desta fase:** e-mail (lixeira = Itens Excluídos) e Teams (sem guardar texto), cada um com plano próprio.
