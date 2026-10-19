# Teams (ness e ionic): aviso de mensagem sem atenção e, depois, propostas

Data: 20/10/2026. Aprovado pelo Ricardo em conversa. Parte 4 de `2026-10-19-graph-ness-design.md`.

## 1. Objetivo
Avisar quando há mensagem para o Ricardo no Teams que ele não atendeu, nas duas contas (resper@ness.com.br e resper@ionic.health). Numa segunda fase, extrair propostas (compromisso, conta a pagar, tarefa) para a fila de aprovação do painel, como a escuta do WhatsApp. Responder pelo Teams é futuro e fora desta spec.

## 2. Restrições
- **R2:** só leitura. Nunca envia, escreve, reage nem apaga. A interface não tem método de escrita.
- **Texto nunca persiste:** corpo, assunto e anexos não entram em tabela, log, exceção nem aviso. Só metadado.
- Só chats em que a conta é membro; a conta vem do cadastro, nunca de entrada livre. (`Chat.Read.All` de aplicativo alcança o tenant todo e não aceita política por caixa; a trava é do código.)
- R5: segredos só nos env já existentes (`/etc/gabi/graph-ness.env`; ionic em `/etc/gabi/graph.env` quando existir).
- Timers instalados desligados; nada é ligado sem o Ricardo. Ionic fica pronto no código e inativo até o administrador do tenant entregar tenant e client id.

## 3. Regra "sem atenção"
- Conta: mensagem de outra pessoa em chat 1:1, ou menção ao Ricardo (`mentions`) em chat de grupo.
- Dispara quando passam **2 horas úteis** desde a mensagem sem resposta do Ricardo posterior a ela (mesma regra nas duas contas). Fora do expediente o aviso espera o início do dia. O expediente e o fuso reutilizam a definição existente do brain (`hoje_brt`); parâmetros em `config`: `teams.horas_uteis` (2), `teams.expediente` (início/fim).
- Um aviso por conversa, não por mensagem. Se o Ricardo responder antes do envio, o aviso fecha como obsoleto (mesmo mecanismo de `revalidar` em `avisos.py`).
- Mensagens do próprio Ricardo, de bots e de sistema não contam.

## 4. Componentes
1. `FonteTeams` (interface só de leitura): `chats(conta)` e `mensagens_recentes(conta, chat_id, desde)` devolvendo só `{id, de_nome, de_eu, quando, mencoes_eu}` (o corpo é descartado na própria fonte na fase 1). Implementações: ness em `graph_ness.py` (secret) e ionic sobre `graph.py` (certificado), inativa sem credenciais.
2. Ponte: métodos novos na lista fixa de `PonteGraph`, com validação da forma da resposta.
3. Tabela `teams_conversa` (migração própria): conta, chat_id, tipo (um_a_um/grupo), `de_nome`, `ultima_para_mim_em`, `minha_ultima_resposta_em`, `ultimo_aviso_em`, cursor. Nenhuma coluna de texto.
4. Coletor (timer, desligado): por conta ativa, lê chats e mensagens novas desde o cursor, atualiza a tabela.
5. Aviso `teams_sem_resposta` em `gabi/avisos.py`, com payload `{conta, tipo, de_nome, desde}` e revalidação pela tabela.
6. Painel: conta Teams no cadastro de fontes (provedor Microsoft) e estado do coletor.

## 5. Entregas
- **Fase 1a:** chats 1:1 e menções em grupo, aviso. Sem modelo.
- **Fase 1b:** menções em canais (listar times e canais dos quais a conta é membro; mais pesado e sujeito a limites do Graph).
- **Fase 2 (gate `teams.classificar`, desligado):** o pipeline da escuta recebe o texto só em memória e devolve propostas para a fila de aprovação; texto descartado. Antes de ligar para a ionic, o Ricardo decide se o conteúdo pode ir ao modelo.

## 6. Erros e limites
Erro do Graph vira `ErroGraph` sem corpo de resposta. 429/Retry-After respeitado; falha de uma conta não derruba a outra. Endpoints de mensagens de chat por aplicativo são sujeitos a licença/medição da Microsoft: verificar em teste real na ness antes de fechar o plano (ponto aberto de verificação, não de decisão).

## 7. Testes
Fixtures do Graph: 1:1 sem resposta, menção em grupo, resposta que fecha o aviso, bot/sistema ignorado, expediente e fim de semana, uma conta com erro e a outra ok, e prova de que corpo/assunto não vazam em log, exceção, aviso nem banco. Depois teste real da ness, só leitura.

## 8. Fora de escopo
Responder ou reagir no Teams (exige ADR de exceção à R2). Escrita de qualquer tipo. Ligar timers. Ionic em produção (depende do administrador).

## 9. Passos do dono
Cadastrar a conta Teams da ness no painel; ligar o timer quando quiser; entregar tenant/client id da ionic quando o administrador liberar.
