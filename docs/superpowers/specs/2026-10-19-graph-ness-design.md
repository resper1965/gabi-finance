# Microsoft Graph da ness (resper@ness.com.br): base, agenda, e-mail e Teams

Data: 19/10/2026. Aprovado pelo Ricardo em conversa: ordem **base → agenda → e-mail → Teams**, cada parte com timer desligado.

## 1. Objetivo e restrições
Ler agenda, e-mail, contatos e Teams da `resper@ness.com.br` (M365) no gabi.brain, no mesmo molde do Google (ADR-017 agenda, ADR-018 correio) e da escuta.
- **Só a caixa `resper@ness.com.br`.** O app (`ness-automacao`) tem permissão de aplicativo para o tenant todo; a restrição é do código (a conta vem do cadastro, nunca de entrada livre) e, fora do código, de política de acesso do Exchange (pendente com o administrador).
- **R2:** o brain nunca envia e-mail nem apaga de vez. Nunca escreve em agenda nem contatos. A única escrita é mover para Itens Excluídos (lixeira do correio), quando for ligada.
- **R5:** segredos só em `/etc/gabi/graph-ness.env`, lidos só pelo serviço de fontes. Nada no banco, no código ou em log.
- Nada é ligado sem o Ricardo. Timers instalados desligados.
- Texto de evento, e-mail ou mensagem do Teams nunca entra em exceção, log ou aviso.

## 2. Estado de fato (verificado em 19/10)
- Tenant `3b1a6aeb-…`, app `ness-automacao`, client credentials com secret. Token OK; leitura de caixa, agenda, contatos e chats da conta deu 200.
- Permissões de aplicativo concedidas: `Mail.ReadWrite`, `Calendars.ReadWrite.All`, `Contacts.ReadWrite`, `Chat.Read.All`, `ChannelMessage.Read.All` (e outras de Teams/SharePoint). Pedido ao Ricardo: trocar por `Calendars.Read` e `Contacts.Read` e tirar `Application.ReadWrite.All` e `Sites.FullControl.All`.
- `gabi/fontes/graph.py` existe (autenticação por certificado, `delta_mensagens`, `delta_eventos`, `criar_rascunho`) e nada o usa. `agenda_fonte.provedor` já aceita `graph`.
- O arquivo `graph-ness.env` tem espaço antes do `=`; vira `KEY=valor` sem espaços.

## 3. Parte 1: base (`gabi/fontes/graph_ness.py`)
- `token_app(env)`: troca `client_credentials` (escopo `https://graph.microsoft.com/.default`) e **cacheia até 5 min antes de expirar**. Erro vira `ErroGraph` sem corpo da resposta.
- `GraphNess`: objeto do serviço de fontes, `__repr__` sem segredos. `graph_ness_do_ambiente(env)` devolve `None` sem as 3 variáveis (fonte "não configurada").
- `contatos(conta)` → `[{nome, telefone, emails}]` no formato de `contato_google` (telefone normalizado como o Google), paginado por `@odata.nextLink`.
- Ponte: `PonteGraph` em `ponte.py` (lista fixa de métodos, validação da forma da resposta), registrada em `ambiente.py` e `servico.py`; `EnvironmentFile=-/etc/gabi/graph-ness.env` na unit, depois dos outros.
- Contatos: `escuta.contas_contatos` passa a aceitar a conta ness com provedor graph. `gabi.contatos` escolhe a fonte pelo provedor da conta.
- Testes: servidor HTTP falso (token, paginação, 401/403/429, resposta malformada, cache do token, nenhum segredo em `repr` e em exceção).

## 4. Parte 2: agenda
- `GraphNess.listar_calendarios(conta)` e `listar_eventos(conta, calendario_id, sync_token, janela)` devolvem o **mesmo formato** do Google (`ResultadoEventos`: eventos, cancelados, `novo_sync_token`, `recarga_completa`). O token é o `deltaLink` do `calendarView/delta` (`Prefer: outlook.timezone="UTC"`).
- Mapeamento: `id`→`externo_id`; `start/end` (+ `isAllDay`) → `inicio/fim` no formato que `tempo.de_google` já entende (data para dia inteiro); `subject`→`titulo`; `onlineMeeting.joinUrl` só se https; `attendees` → `participantes_qtd`; `sensitivity` private/confidential → `privado`; `showAs=free` → `livre`; `iCalUId` → `ical_uid`; `isCancelled` e `@removed` → `cancelados`; evento recusado pelo dono (`responseStatus.response=declined` do próprio) é pulado.
- `sincronizar` aceita `provedor='graph'` com `auth='oauth'` (rótulo existente) e usa `PonteGraph.listar_eventos`; erros 401/403 reusam o aviso `agenda_reconectar`. Janela e recarga de 7 dias iguais às do Google. 410/`resyncRequired` → recarga completa.
- Painel: Cadastros › Agenda aceita conta do tipo Microsoft; "Descobrir calendários" e "Liberar" iguais. Timer `gabi-brain-agenda` é o mesmo (lê todas as fontes liberadas); continua desligado.
- Testes: golden de um dia comum, dia inteiro, recorrente, cancelado, privado, recusado; recarga; delta; erro.

## 5. Parte 3: e-mail (spec própria, depois da agenda)
Provedor `microsoft` no correio sobre `delta_mensagens`; lixeira = mover para Itens Excluídos (`/move` com `deleteditems`); nunca `DELETE`. Mesmo cadastro de caixa e as mesmas regras do ADR-018. Desenho fino na spec da parte.

## 6. Parte 4: Teams (spec própria, por último)
Leitura de chats e canais com `Chat.Read.All`/`ChannelMessage.Read.All`; classificação pelo modelo e **sem guardar o texto** (modelo da escuta). Atenção: essas permissões de aplicativo alcançam o tenant todo e não aceitam política de restrição por caixa; o código só lê os chats em que a conta da ness é membro. Desenho fino na spec da parte.

## 7. Fora de escopo
Ionic (continua parado, não mexer). Escrita em agenda/contatos. Envio de e-mail. Certificado (a ness usa secret). Ligar qualquer timer.

## 8. Passos do dono
Remover as permissões a mais do app; pedir ao administrador a política de acesso do Exchange para `resper@ness.com.br`; instalar; cadastrar a conta no painel; ligar o timer quando quiser.
