# Envios com anuência: marcar agenda e escrever no Teams (AT1)

Data: 22/10/2026 · ADR: `docs/adr/024-envios-com-anuencia.md` · Item: AT1 do `docs/BACKLOG.md`

## Objetivo
O Ricardo pede ao Hermes "marca com Fulano quinta 15h pela ness" ou "posta no canal X: ...". O brain monta o envio exato, o Ricardo confere e aprova no painel, e só então o envio sai. É a primeira exceção à R2 (nenhum envio externo automático): nada sai sem um clique do Ricardo naquele envio específico.

## Decisões do Ricardo (22/10)
1. Quem inicia: **só o Ricardo, pelo Hermes**. O brain não sugere envio sozinho.
2. Agenda: **criar evento com convidados** (o convite sai por e-mail para os convidados). Não remarca, não cancela, não responde convite.
3. Contas de agenda: **`resper@ness.com.br` (Graph), `resper@bekaa.eu` e `resper@gmail.com` (Google)**.
4. Teams (só ness): **escrever em chat que já existe e postar em canal de equipe** da qual ele é membro. Não abre conversa nova.
5. Onde o "sim" é dado: **no painel** (botão Enviar). O Hermes só propõe; não existe ferramenta MCP que aprove ou envie.

## Fluxo
1. O Hermes chama `propor_evento` ou `propor_teams` (MCP, escopo novo `envios`).
2. O brain valida e resolve: conta permitida, horário, convidados por e-mail e destino do Teams. Depois grava uma linha em `envio_proposta` (`pendente`) com o conteúdo canônico, o hash desse conteúdo e uma `chave` aleatória de idempotência. Devolve id, resumo e o link do painel.
3. A tela **Envios** do painel lista as pendentes com tudo o que vai sair e oferece os botões Enviar e Recusar.
4. **Enviar** (`POST /api/v1/envios/{id}/enviar`, corpo `{"hash": ...}`): revalida, passa `pendente → enviando` de forma atômica, chama o provedor pela ponte e grava `enviada`, `falhou` ou `incerto`. O painel mostra o resultado na hora. Auditoria em `decisao` (origem `envios`) na mesma transação da decisão.

## Modelo de dados: migração 0076 `envio_proposta`
| coluna | uso |
|---|---|
| `id` integer pk | |
| `tipo` | `evento` \| `teams_chat` \| `teams_canal` |
| `conta` | conta de origem (minúscula) |
| `conteudo` | JSON canônico (`sort_keys`, sem espaços) do que sai; não muda depois de criado |
| `hash` | sha256 do `conteudo` |
| `chave` | 26 caracteres base32hex minúsculos, aleatória: id do evento no Google, `transactionId` no Graph |
| `estado` | `pendente` · `enviando` · `enviada` · `recusada` · `falhou` · `incerto` · `vencida` |
| `motivo` | código fixo da falha (nunca texto de exceção) |
| `externo_id` | id do evento ou da mensagem devolvido pelo provedor |
| `criada_em`, `vence_em`, `decidida_em`, `decidida_por`, `enviada_em` | UTC ISO |

Os estados finais são `enviada`, `recusada`, `falhou`, `incerto` e `vencida`. `vence_em` = criada + 24h. Num evento, vence também quando o início passa: o menor dos dois prazos.

**Conteúdo de `evento`:** `{conta, provedor ("graph"|"google"), titulo, inicio_utc, fim_utc, fuso: "America/Sao_Paulo", convidados: [e-mail...], descricao?, online: bool}`. Com `online`, a ness ganha link do Teams (`isOnlineMeeting`) e o Google ganha link do Meet (`conferenceData.createRequest`, `requestId` = chave).
**Conteúdo de `teams_chat`:** `{conta, chat_id, destino_nome, tipo, texto}` (`tipo` = `um_a_um` | `grupo`, de `teams_conversa`: `de_nome` é quem escreveu por último, então o chat pode ser de grupo; o cartão e o resumo mostram "(grupo)"; propostas antigas sem `tipo` ficam sem aviso). **De `teams_canal`:** `{conta, equipe_id, canal_id, equipe_nome, canal_nome, texto}`.

## Configuração (dados, não código)
- `parametro envios.escrita`: só `"ligado"` liga, o padrão é desligado. Desligado, a proposta é criada e listada, mas Enviar responde 409 `envios_desligados` e não chama nenhum provedor.
- `parametro envios.contas_agenda`: lista JSON das contas onde se pode criar evento. O padrão é vazio, e o Ricardo grava as três contas no passo do dono. O provedor de cada conta sai de `agenda_fonte.provedor` (calendário `primary`). Conta fora da lista ou sem `agenda_fonte` é recusada.
- Teams: a conta precisa estar em `teams_fonte` com `estado='sim'` e na `M365_CONTAS` do serviço de fontes.

## Ferramentas MCP (escopo `envios`, entram em `ESCOPOS_HERMES`)
- `propor_evento(conta, titulo, inicio, duracao_min, convidados: list[str], descricao="", online=True)`. `inicio` é ISO local de Brasília, sem fuso ou com `-03:00`. `duracao_min` vai de 5 a 720. Cada convidado é um e-mail ou um nome. Nome casa sem diferença de caixa e acento com o nome de contato que o brain já tem (`contato_google` + `contato_google_email`, qualquer conta). Se o nome der 0 ou mais de 1 e-mail, nada é gravado e volta `convidado_ambiguo` com os candidatos (nome e e-mail) para o Hermes perguntar ao Ricardo. O limite é de 1 a 30 convidados, e o título tem de 1 a 200 caracteres.
- `propor_teams(texto, chat_com="", equipe="", canal="")`: exatamente um destino. **Chat:** `chat_com` casa com `teams_conversa.de_nome` da conta (sem caixa e acento); 0 ou mais de 1 chat dá `destino_ambiguo` com os candidatos. **Canal:** equipe e canal são resolvidos por nome na lista viva (`teams_equipes`/`teams_canais` pela ponte, token delegado). O texto vai de 1 a 4000 caracteres e sai como texto simples (`contentType: text`), nunca HTML.
- Nenhuma das duas envia. A resposta traz `{id, estado: "pendente", resumo, link}`. O `link` vem de `parametro painel.url` mais `#envios`; sem o parâmetro, vem só o id. O painel passa a abrir na área indicada pelo `#` da URL, quando ela existe.
- O teste que fixa a lista do MCP passa de 18 para 20 ferramentas.

## Rotas da API (`/api/v1/envios`, só boss)
- `GET ?estado=pendente`: itens com `conteudo` legível, `hash`, `vence_em` e `escrita` (ligado ou desligado). Ao listar, as pendentes vencidas viram `vencida`.
- `POST /{id}/enviar {hash}`: 404 se não existe; 409 `conflito` se não está `pendente`; 409 `vencida`; 409 `envios_desligados`; 409 `hash_diferente` se o hash não bate. Revalida a conta, que precisa continuar permitida; se não, grava `falhou` com motivo `conta_nao_permitida`. A transição atômica é `update ... set estado='enviando' where id=? and estado='pendente'`. Se o rowcount for 0, responde 409 e não envia.
- `POST /{id}/recusar`: `pendente → recusada`; 409 se não está pendente.

## Envio (ponte e serviço de fontes)
- **Google:** `GoogleAgenda.evento_criar(conta, chave, evento)` faz `POST calendars/primary/events?sendUpdates=all[&conferenceDataVersion=1]` com `id=chave`. Um 409 (o id já existe) conta como `enviada` (idempotência). O escopo `calendar.events` entra no `tools/obter_token_google.py`, mantendo `calendar.readonly`.
- **Graph agenda:** `graph_ness_envios.evento_criar(fonte, conta, chave, evento)` faz `POST /users/{conta}/events` com `transactionId=chave`, `attendees` required e, se `online`, `isOnlineMeeting=true` e `onlineMeetingProvider=teamsForBusiness`. Usa o token de aplicativo (`Calendars.ReadWrite`). O Exchange manda os convites.
- **Graph Teams (delegado):** `TokenDelegado` troca `GRAPH_NESS_TEAMS_REFRESH` (env do serviço, colocado pelo Ricardo) por access token no tenant da ness, com cliente público. O refresh token novo que a Microsoft devolve fica **só em memória**. Depois de um reinício vale o do env, que dura até 90 dias do login. Métodos: `teams_equipes(conta)` (`/me/joinedTeams`), `teams_canais(conta, equipe_id)`, `teams_chat_enviar(conta, chat_id, texto)` e `teams_canal_enviar(conta, equipe_id, canal_id, texto)`. Token recusado dá o motivo `login_teams_expirado`. A conta do token delegado precisa ser a mesma da proposta (confere pelo `/me` ao obter o token).
- Esses métodos ficam em `gabi/fontes/graph_ness_envios.py`, um arquivo separado. Assim a varredura de `graph_ness.py`, que proíbe enviar e postar, continua valendo, e uma varredura nova fixa em `graph_ness_envios.py` só estes métodos e só estes verbos e URLs. A lista branca `PERMITIDOS` da ponte ganha só esses nomes.
- **Resultado:** ok dá `enviada` com `externo_id`. Erro HTTP com status (4xx ou 5xx) dá `falhou` com `motivo = provedor_<status>`. Timeout ou ponte fora do ar dá `incerto` (estado final, em qualquer provedor): o Ricardo confere na agenda ou no Teams. O brain nunca reenvia sozinho. O 409 do Google como `enviada` e o `transactionId` do Graph protegem contra repetição dentro da mesma chamada do provedor.

## Painel
Área nova **Envios** no grupo Dia ("O que espera meu OK para sair?"). Cada cartão mostra o tipo, a conta, o título ou destino, o horário em Brasília, os e-mails dos convidados, o texto completo e quando vence, com os botões Enviar e Recusar. O Enviar manda o `hash` que veio na listagem. Uma faixa avisa quando `envios.escrita` está desligado. Abaixo das pendentes ficam as últimas 20 decididas, com estado e motivo.

## Segurança e privacidade
- R14: texto de terceiros é dado. A única coisa que vira envio é o que o Ricardo pediu, e mesmo isso só depois do clique dele.
- Logs e `decisao` registram o id, o tipo, a conta e o estado. Nenhum título, texto, nome ou e-mail vai para log, stderr ou auditoria.
- Risco aceito, o mesmo modelo da ADR-020: os métodos novos da ponte não conferem aprovação, e quem tem o socket do serviço de fontes pode chamá-los. As travas ficam na rota. A permissão de app `Calendars.ReadWrite` alcança o tenant da ness inteiro; a barreira é `M365_CONTAS` mais `envios.contas_agenda`.

## Testes
Sem rede, com provedores falsos:
- Validação e resolução das ferramentas, incluindo os casos de ambiguidade.
- Hash e conteúdo imutável.
- Validade: 24h e início no passado.
- Interruptor desligado sem chamada ao provedor.
- Duplo Enviar com uma única chamada.
- Google 409 tratado como enviada.
- Timeout do Teams como `incerto`, sem repetir.
- Revalidação da conta.
- Auditoria sem conteúdo.
- Varredura de `graph_ness_envios.py`.
- Lista de métodos da ponte e lista de ferramentas do MCP, que continua sem aprovar.
- Escopos do token Google.
- Tela Envios no vitest.

## Passos do dono (depois do merge, com runbook `#envios`)
1. No Entra da ness, app `ness-automacao`, trocar `Calendars.Read` por `Calendars.ReadWrite` (aplicativo) e adicionar as delegadas `ChatMessage.Send`, `ChannelMessage.Send`, `Team.ReadBasic.All`, `Channel.ReadBasic.All` e `offline_access`, com o consentimento dado. Ativar "Permitir fluxos de cliente público".
2. Rodar `tools/obter_token_teams.py` (fluxo de código de dispositivo) e gravar `GRAPH_NESS_TEAMS_REFRESH` no env do serviço de fontes.
3. Rodar `tools/obter_token_google.py` de novo para gmail e bekaa (agora com `calendar.events`).
4. Dar ao token MCP do Hermes o escopo `envios` e incluir as 2 ferramentas novas em `~/.hermes/config.yaml`.
5. Gravar `envios.contas_agenda` e `painel.url` e ligar `envios.escrita`.

## Fora desta fase
Remarcar, cancelar ou responder convite; conversa nova no Teams; ionic; backoffice@bekaa.eu; o brain sugerir envio; aprovar pelo chat ou pelo Telegram; e-mail. Entram só se fizerem falta depois de um mês de uso.
