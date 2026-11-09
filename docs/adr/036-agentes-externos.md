# ADR-036 · Agentes externos: chaves e receitas de conexão pelo painel

Data: 09/11/2026 · Estado: aceito (implementado na branch `feat/agentes-externos`, aguarda ok de merge e instalação) · Spec: `docs/superpowers/specs/2026-11-09-agentes-externos-design.md` · Plano: `docs/superpowers/plans/2026-11-09-agentes-externos.md`

**Contexto.** O MCP já atende o Hermes, mas emitir, trocar escopo e revogar chave só existia por linha de comando na VPS. O Ricardo quer ligar ao brain os seus próprios agentes (Claude Code, Cursor, Codex CLI etc.) nas suas máquinas, sem passar pelo terminal da VPS.

**Decisões do Ricardo (09/11).**
1. **Só agentes dele, dentro da Tailscale.** Nada novo exposto na internet. OpenAI API e agentes em nuvem (exigem URL pública) ficam de fora, e a tela diz isso.
2. **Permissões:** toda chave nova nasce com os mesmos escopos do Hermes (`ESCOPOS_HERMES`), sem `sensivel`; ele desmarca o que não quiser. Sem perfis prontos.

**O que foi feito.** API `/api/v1/agentes` (`gabi/rotas/agentes.py`: listar, emitir, trocar escopos, revogar, rotacionar, chamadas, `conexao`), regras em `gabi/agentes.py` (cada ação auditada) e a tela Gabi › Agentes com receitas por cliente (`painel/src/telas/Gabi/Agentes.tsx` e `receitas.ts`). A chave aparece uma vez, ao emitir ou rotacionar; o banco guarda só o hash. Rotacionar emite a nova e revoga a antiga na mesma transação. Revogar ou rotacionar a chave do Hermes pede confirmação reforçada. Nenhuma ferramenta MCP nova (continuam 71) e nenhuma migração.

**Fora.** Validade de chave, limite de chamadas, ferramentas por chave, OAuth no MCP, URL pública, chaves para outras pessoas, perfis de permissão.

**Risco aceito.** Por padrão, uma chave nova tem escopos de escrita (os do Hermes); quem a tem altera dados do brain, dentro das regras de anuência (R2: envios só no clique dele). A defesa é a rede (só tailnet), a revogação pelo painel e o registro de cada chamada. Rotacionar ou revogar a chave do Hermes derruba Telegram e WhatsApp até o `config.yaml` do Hermes receber a nova.

**Desfazer.** `git revert` do merge e `sudo ~/instalar-brain.sh`; chaves emitidas podem ser revogadas antes, pelo painel.
