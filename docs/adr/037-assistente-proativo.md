# ADR-037 · Assistente proativo: promessas, olhar à frente, preparo de reunião e revisão da semana

Data: 09/11/2026 · Estado: aceito (implementado na branch `feat/assistente-proativo`, aguarda ok de merge e instalação) · Spec: `docs/superpowers/specs/2026-11-09-assistente-proativo-design.md` · Plano: `docs/superpowers/plans/2026-11-09-assistente-proativo.md`

**Contexto.** Perguntado o que ele esperaria de um assistente seu, o Ricardo aprovou três direções: que nada que ele prometeu se perca, ser avisado antes do problema e receber o trabalho pronto para só decidir. Regras que seguem valendo: o brain sugere e o Ricardo decide (R1), nada sai sem o clique dele (R2), pergunta vai para o Hermes e nada vira sistema antes de um mês de uso manual (ADR-023).

**Decisão.** Quatro ferramentas MCP **só de leitura** (71 para 75), sem migração, sem timer e sem tela:
1. `promessas_candidatas(dias)` (escopo `trabalho`): lê ao vivo os e-mails enviados (Gmail e Graph da ness), sem gravar nada; o Hermes procura compromissos e só cria `atividade_criar` depois do sim do Ricardo.
2. `olhar_a_frente(dias)` (escopo `fin`): caixa projetado que fica negativo, a receber atrasado há 10 dias ou mais, documentos em 30 dias, atividades em 7. O resumo da manhã ganha o bloco "Olhando à frente" só quando há alerta; falha do bloco nunca derruba o resumo.
3. `preparar_reuniao(evento)` (`trabalho`): contatos, atividades, projetos, a receber e e-mails pelo assunto do título (a agenda não guarda quem participa; `termos_usados` mostra o que casou).
4. `revisao_semana()` (`trabalho`): o que andou e o que parou.
O rascunho de resposta de e-mail é só instrução no SOUL (no chat, sem envio).

**Mudança de limite deliberada.** Até aqui a ponte devolvia dos enviados só endereços. Entra `enviados_textos` (Gmail e Graph, só GET): `para` (até 5), `assunto` e trecho de 600 caracteres do que o Ricardo escreveu (corta na citação), 30 mensagens por conta, janela de 1 a 14 dias. O texto não é gravado nem logado. O Teams continua sem texto lido.

**Segurança.** Texto de e-mail é dado de terceiros (aviso em toda resposta). Nenhuma ferramenta escreve; criar atividade é passo separado, a pedido dele no chat (R14). Escopos já presentes em `ESCOPOS_HERMES`: não precisa trocar token. Um agente externo com `trabalho` passa a poder ler trechos dos enviados; a tela Gabi › Agentes deixa desmarcar.

**Fora.** Aviso automático de promessa, timer, tabela, tela, Teams, envio de e-mail, extração por modelo dentro do brain. Cada um só entra depois de um mês de uso das ferramentas.

**Numeração.** A branch `feat/projetos-melhorias` planeja 73 ferramentas e outro ADR-035: quem mergear depois renumera (contagem e ADR).

**Desfazer.** `git revert` do merge e `sudo ~/instalar-brain.sh`; Hermes: voltar `~/.hermes/config.yaml.bak-antes-assistente` e o SOUL (`SOUL.md.bak-<data>`), reiniciar o `hermes-gateway`.
