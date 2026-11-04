# Convites de agenda recebidos: aviso, conflito e resposta com um clique (design)

Data: 04/11/2026 · Dono: Ricardo · Estado: aguardando revisão do spec

## Objetivo
Convite recebido vira uma decisão do Ricardo em um toque, com o conflito de horário à vista.
Sucesso: ele recebe o aviso, vê se há conflito, clica uma vez no painel e o convite é respondido na conta certa.

## Decisões do Ricardo (04/11)
- Escopo = convites que **chegam** (não os que ele manda).
- O único lugar de aprovação é o **painel › Envios** (como o AT1, ADR-024). Botão no Telegram e "diga ao Hermes e confirme" ficam fora desta fase.

## Premissas (a confirmar na revisão)
- Contas = as de `envios.contas_agenda` (hoje só `resper@ness.com.br`, Graph). Gmail e Bekaa entram quando ele ligar essas contas.
- Respostas: aceitar, talvez, recusar, sem comentário. Remarcar e propor outro horário ficam fora.
- Convite de série (recorrente): a resposta vale para a série inteira.

## Restrições
- R2 (nada sai sem o clique): responder convite é envio externo e só sai no clique, coberto pelo ADR-024. Exige um ADR curto (035) que amplie o ADR-024 a "responder convite".
- ADR-023: sem tabela, timer ou unit novos. Estende `agenda_evento`, `gabi-brain-avisos` e a fila de Envios.
- Privacidade: continuam sem ser guardados os e-mails dos outros participantes; guarda-se só o nome do organizador.
- Esquema novo = migração 0088.

## Dados
`agenda_evento` ganha:
- `resposta` (texto): `needsAction`, `accepted`, `tentative`, `declined` ou vazio (eventos antigos e eventos que ele organiza).
- `organizador_nome` (texto), só o nome.
- `serie_id` (texto): id do evento-mestre quando o evento é de uma série.

A sincronização do Graph (`graph_ness.py`, trecho de `attendees`/`responseStatus`) preenche os campos. O Google já tem o `self.responseStatus`, mas fica fora desta fase.
**Convite pendente** = evento futuro com `resposta='needsAction'` e que ele não organiza.
**Conflito** = calculado na leitura: outro evento dele, aceito ou pendente, que se sobreponha no tempo. Nada é gravado.

## Aviso
`gabi-brain-avisos` gera um aviso por convite pendente, com deduplicação pelo id do evento; muda o horário, avisa de novo.
Texto: `Convite: <título> · qui 15h–16h · de <organizador> · conflita com <evento>` ou `· sem conflito`, com o link do painel › Envios.

## Resposta (fluxo de envio)
1. **Proposta.** A ferramenta MCP `propor_resposta_convite(conta, evento_id, resposta)` (`aceitar|talvez|recusar`, escopo `envios`, que o token do Hermes já tem) grava a proposta na fila de Envios. Valida antes: evento existe e é futuro; conta está em `envios.contas_agenda`; ele não é o organizador. Não pode haver duas propostas abertas para o mesmo convite. O painel também cria a proposta pelos botões da lista de convites.
2. **Clique em Enviar.** `convite_responder` em `graph_ness_envios.py`, com a mesma conta delegada e a chave de idempotência do `evento_criar`, chama `POST /me/events/{id}/accept`, `/tentativelyAccept` ou `/decline`, com `sendResponse: true` e sem comentário. Para série, usa o `serie_id`.
3. **Depois.** A proposta fica "enviada"; a próxima sincronização atualiza `resposta`.

## Erros e limites
- 404/409 do Graph (já respondido ou apagado): proposta "obsoleta", sem repetir o envio.
- Série não encontrada: a proposta falha com mensagem clara e nada é enviado.
- Token vencido: vale o mecanismo existente (renova uma vez); se falhar, a proposta fica pendente com o erro, sem corpo nem segredo em log.
- Conflito não bloqueia: ele pode aceitar com conflito; o painel só mostra o aviso ao lado dos botões.
- Fora desta fase: comentário na resposta, propor outro horário, convites no Google, botões no Telegram.

## Testes
- Camada do Graph com HTTP falso (padrão do `evento_criar`): aceitar, talvez, recusar, 404, 409, série.
- Ferramenta: organizador recusado, conta fora da lista, evento passado, proposta duplicada.
- Sincronização: leitura de `responseStatus`, organizador e série; cálculo de conflito.
- Aviso: uma vez por convite e de novo se mudar o horário.
- Painel: lista de convites e botões (vitest).
- Teste real, do Ricardo: o Hermes propõe e ele clica em Enviar.

## Instalação (depois da aprovação, pelo runbook)
Migração 0088, ADR-035, `propor_resposta_convite` no include do Hermes (nova contagem de ferramentas), SOUL, reinício do `hermes-gateway`, `/new` nos dois canais. Backup do banco antes. Nada instala sem o ok dele.
