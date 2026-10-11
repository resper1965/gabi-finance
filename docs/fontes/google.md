# Fonte: Google (Gmail, Agenda, Tasks) — `gabi/fontes/google.py` (T3.2, gate G12)
- **4 contas Google.** Conta de serviço com delegação para domínio: bekaa.eu e esper.ws (`assertion_servico` monta o JWT; `sub` = caixa). OAuth próprio: ness e Gmail (refresh token no arquivo de ambiente, nunca no banco). Composio **não** serve: aceita uma conta só.
- **Incremental:** `historico_gmail(caixa, start_history_id)`; se o histórico expirou (404) faz **um** resync completo das últimas 200 mensagens e devolve o historyId atual. Agenda por `syncToken`.
- **R2:** só lê e cria rascunho (`drafts`); sem envio e sem exclusão.
- **Dedupe com o Graph:** `message_id` (cabeçalho Message-ID) é único em `item_email`; a migração da ness não duplica.
- **Estado:** cliente pronto e testado contra servidor falso. **Não validado com contas reais** (falta G12).

## Contatos do Google (`gabi/fontes/google_contatos.py`, módulo escuta)
- **Só nome e telefone, só leitura.** People API `people/me/connections`, `personFields=names,phoneNumbers`, escopo `https://www.googleapis.com/auth/contacts.readonly`, todas as páginas. Nunca foto, e-mail, endereço ou nota; o brain não escreve nos contatos.
- **Duas contas** (parâmetro `escuta.contas_contatos`, JSON; padrão `resper@gmail.com` e `resper@ness.com.br`). O Gmail pessoal não aceita delegação de conta de serviço: cada conta usa OAuth com refresh token próprio.
- **Segredos** só no serviço `gabi-brain-fontes`, em `/etc/gabi/google-contatos.env` (EnvironmentFile opcional; você coloca, o código nunca cria nem lê): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REFRESH_<CONTA>`, onde `<CONTA>` é a conta em maiúsculas com tudo que não é letra/número trocado por `_` (ex.: `GOOGLE_REFRESH_RESPER_GMAIL_COM`, `GOOGLE_REFRESH_RESPER_NESS_COM_BR`). Sem `GOOGLE_CLIENT_ID`/`SECRET` a fonte é "não configurada" (API 503 `fonte_indisponivel`). Conta sem refresh token: erro `conta não autorizada: <conta>`.
- **Ponte:** `PonteContatos(socket).listar(conta)`; API, MCP e o timer `gabi-brain-contatos` (05:00 BRT, instalado e desligado) não têm rede nem segredo.
- **Dados:** `contato_google(conta, telefone, nome)` com telefone em E.164; `DELETE /api/v1/escuta/contatos` apaga tudo (revogar). Exportação "só na ness": `GET /api/v1/escuta/contatos/so-na-ness.csv` (origem `escuta.conta_origem_contatos`, destino `escuta.conta_destino_contatos`; colunas `Name,Phone 1 - Value`, importável em contacts.google.com).
