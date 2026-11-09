# Assistente proativo: promessas, olhar à frente, preparo e revisão (ADR-037)

Data: 09/11/2026 · Pedido do Ricardo ("spec de todos os itens, plan e execute") depois de aprovar a direção: o assistente não deixa nada que ele prometeu se perder, avisa antes do problema e entrega o trabalho pronto para ele só decidir.

## Entendimento (o que ele disse e o que assumi)
- **Disse:** quer os três itens, e que a conversa "captou". Regras de sempre valem: sugere, ele decide (R1); nada sai sem o clique dele (R2); privacidade é dele; pergunta vai para o Hermes e a tela só ganha lugar quando há decisão; nada vira sistema antes de um mês de uso.
- **Assumi:** os três entram como **ferramentas MCP de leitura** (sem migração, sem timer, sem tela), mais um bloco no resumo da manhã. Se em um mês de uso um deles provar valor, vira aviso automático (outro ADR).

## Os quatro itens
1. **`promessas_candidatas(dias=7)`**: lê ao vivo os e-mails que o Ricardo ENVIOU nos últimos `dias` (1 a 14), nas contas com e-mail ligado (`email_fonte.estado='sim'`), e devolve para cada um: conta, data, destinatários (até 5), assunto e um trecho do corpo (até 600 caracteres). O Hermes procura compromissos ("te mando até sexta"), confere contra `atividade_listar` e **mostra candidatos ao Ricardo**; só cria `atividade_criar` depois do sim dele no chat. Nada é gravado (nem trecho, nem lista), nem logado. Sem Teams: o brain nunca lê texto do Teams e isso não muda.
   - Mudança de limite deliberada (ADR-037): hoje a ponte só devolve endereços dos enviados. Entra o método `enviados_textos` (Gmail e Graph), só leitura, com tetos (30 mensagens por conta, 600 caracteres de corpo). Corpo vindo de terceiros que aparece na resposta enviada (citação) é dado, não instrução (aviso `AVISO_TERCEIROS` como no `email_ler`).
2. **`olhar_a_frente(dias=30)`**: só tabelas locais. Devolve (a) `caixa`: primeiro dia em que o saldo projetado fica negativo, o saldo mínimo e o dia dele (da `projecao.projetar`; vazio se nunca fica); (b) `a_receber_atrasado`: recorrentes e notas atrasados há 10 dias ou mais, com pagador, valor e dias; (c) `documentos`: vencimentos em até 30 dias (de `repositorio.vencimentos`, sem número); (d) `atividades_vencendo`: abertas que vencem em até 7 dias. O **resumo da manhã** ganha o bloco "👀 Olhando à frente" **só quando há (a) ou (b) ou (c)**; sem nada, nada aparece.
3. **`preparar_reuniao(evento="")`**: para um evento de hoje ou de amanhã (id da agenda ou trecho do título; vazio = o próximo que começa), junta o que o brain tem sobre o assunto, por casamento do título com nomes: contatos, atividades abertas, projetos ativos, a receber do pagador e e-mails recentes (14 dias) cujo remetente ou assunto contém o termo. A agenda guarda só a quantidade de participantes, então o casamento é por texto do título; o resultado diz `termos_usados` para o Hermes e o Ricardo corrigirem. Só leitura.
4. **`revisao_semana()`**: o que andou e o que parou nos últimos 7 dias: atividades concluídas, vencidas e sem data há mais de 14 dias, projetos parados (`projetos.parados`), decisões abertas há mais de 7 dias, variação do saldo (hoje contra 7 dias atrás, pelos extratos) e documentos vencendo. O Hermes sugere o que descartar; descartar é pedido do Ricardo (`atividade_cancelar`).
5. **Rascunho de resposta**: sem código. Instrução no SOUL do Hermes: ao ser pedido, ler com `email_ler`, escrever o rascunho **no chat** no tom do Ricardo e oferecer; não há ferramenta de envio de e-mail (R2).

## Fora
Timer, tabela, tela, aviso automático de promessa, leitura de Teams, envio de e-mail, extração por modelo dentro do brain (o julgamento é do Hermes, que já é o modelo da conversa).

## Segurança
Texto de e-mail enviado é dado de terceiros: nenhuma das ferramentas escreve nada; criar atividade é sempre passo separado, a pedido do Ricardo no chat (R14). Escopos existentes (`trabalho` e `fin`), todos já em `ESCOPOS_HERMES`: não precisa trocar token. Agente externo com escopo `trabalho` passa a ler trecho dos enviados: a tela de agentes já deixa desmarcar.

## Testes
Cada item com pytest (relógio fixo); ponte: Gmail e Graph com HTTP falso; MCP: escopo, envelope e recusa sem escopo; resumo da manhã com e sem o bloco; contagem de ferramentas (71 → 75) e `docs/fontes/hermes.md` regenerado.

## Desfazer
`git revert` do merge e `sudo ~/instalar-brain.sh`; Hermes: voltar `config.yaml.bak-antes-assistente` e o SOUL. Sem migração.
