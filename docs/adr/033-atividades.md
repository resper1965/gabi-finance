# ADR-033 · Atividades: recado ao Hermes vira to-do, com lista no painel e aviso no Telegram

Data: 27/10/2026 · Estado: aceito (implementado na branch `feat/atividades`, aguarda autorização de merge e instalação) · Spec: `docs/superpowers/specs/2026-10-27-atividades-design.md` · Plano: `docs/superpowers/plans/2026-10-27-atividades.md`

**Contexto.** O Ricardo quer um to-do pessoal: deixa um recado num canal e o Hermes cria uma atividade. Sem aviso a lista vira papel esquecido.

**Decisões (Ricardo, 27/10).**
1. **Depois de criada:** lista no painel mais lembrete no Telegram (não Google Tasks, Microsoft To Do nem Linear).
2. **Como deixar o recado:** mensagem normal ao Hermes, no Telegram ou no WhatsApp; ele interpreta, cria e confirma numa linha. Sem canal dedicado.
3. **Quando avisar:** no horário dito (se tiver hora), uma vez de manhã no dia do vencimento e um resumo diário às 07:00 com vencidas, as de hoje e as sem data. Sem insistir todo dia.

**Como ficou.**
- Tabela própria `atividade` (migração 0086), separada da `tarefa` do módulo Trabalho cortado na ADR-023. `vence_em` em UTC; `tem_hora=0` guarda o dia todo (00:00 de Brasília).
- Regras em `gabi/atividades.py`; API (`/api/v1/atividades`), MCP e painel só chamam daí. Criar igual a uma aberta devolve a existente (`ja_existia`), para o Hermes repetir sem duplicar. Não existe reabrir: para voltar, cria de novo.
- **Avisos pelo produtor existente** (`gabi/avisos.py`, timer de 15 min) e a entrega do Telegram: três tipos novos (`atividade_hora`, `atividade_hoje`, `atividade_resumo`), revalidados na entrega (atividade feita, cancelada ou adiada fecha o aviso sem enviar). Precisão do aviso na hora: até 15 min. Só o Telegram entrega; o WhatsApp só recebe o recado.
- MCP (escopo novo `atividades`, `gabi/mcp/ferramentas_atividades.py`): `atividade_criar`, `atividade_listar`, `atividade_concluir`, `atividade_adiar`, `atividade_cancelar`; 60 ferramentas no include. Criar **não pede sim antes** (é reversível, e o Hermes diz a data que entendeu); só a pedido do Ricardo no chat, nunca por texto de e-mail, Teams ou documento.
- Painel: grupo Dia › Atividades (Vencidas, Hoje, Próximas, Sem data; Feita, Adiar, Excluir com confirmação).

**Consequências.** O token do Hermes precisa do escopo `atividades` (passo do runbook). Resumo e aviso "para hoje" repetem a informação de propósito (decisão aprovada).

**Fora.** Integração com Google Tasks, Microsoft To Do e Linear; atividades recorrentes; insistência diária em vencida; reabrir; aviso por WhatsApp.

**Desfazer.** Backup `gabi.db.antes-atividades-<data>`; `git revert` do merge e `sudo ~/instalar-brain.sh`; no Hermes, restaurar `config.yaml.bak-antes-atividades` e o SOUL (`SOUL.md.bak-<data>`), `sudo systemctl restart hermes-gateway` e `/new`. A tabela nova é inofensiva se ficar.
