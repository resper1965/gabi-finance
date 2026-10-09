# Fonte: Google (Gmail, Agenda, Tasks) — `gabi/fontes/google.py` (T3.2, gate G12)
- **4 contas Google.** Conta de serviço com delegação para domínio: bekaa.eu e esper.ws (`assertion_servico` monta o JWT; `sub` = caixa). OAuth próprio: ness e Gmail (refresh token no arquivo de ambiente, nunca no banco). Composio **não** serve: aceita uma conta só.
- **Incremental:** `historico_gmail(caixa, start_history_id)`; se o histórico expirou (404) faz **um** resync completo das últimas 200 mensagens e devolve o historyId atual. Agenda por `syncToken`.
- **R2:** só lê e cria rascunho (`drafts`); sem envio e sem exclusão.
- **Dedupe com o Graph:** `message_id` (cabeçalho Message-ID) é único em `item_email`; a migração da ness não duplica.
- **Estado:** cliente pronto e testado contra servidor falso. **Não validado com contas reais** (falta G12).
