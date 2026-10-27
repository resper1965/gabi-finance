# Handoff — estado em 27/10/2026 (para retomar em outra sessão ou outro modelo)

Leia antes: `docs/STATUS.md`, `docs/BACKLOG.md` (fonte única do que falta), `docs/runbook.md`, `docs/PLANO-DEFINITIVO.md`.
Regras do Ricardo que valem sempre: resumos curtos; nunca reabrir decidido ou on hold; o assistente faz o trabalho (não pedir que ele anote/preencha);
privacidade é dele (não mascarar dado); **nunca mexer em despesa/ocorrência paga**; nada instala/merge sem ok explícito dele;
Gabi = projeto, brain = app, Hermes = agente. Ele não consegue colar texto no terminal: fluxos interativos (OAuth) eu rodo em segundo plano
e ele cola a URL final num arquivo (`~/chavegoogle.txt`, apagar depois) ou digita código de dispositivo.

Produção: banco `/var/lib/gabi-brain/gabi.db` (ler/escrever só com `sudo -u gabibrain /opt/gabi-brain/venv/bin/python`, cd /tmp ou /opt/gabi-brain);
instalar = `sudo ~/instalar-brain.sh` (copia main para /opt). Toda escrita manual no banco: backup antes e linha em `decisao`.

## 1. Item 3 — CRUD de despesas (branch `feat/despesas-crud`, NÃO mergeada, NÃO instalada)
- Spec `docs/superpowers/specs/2026-10-26-despesas-crud-design.md`, plano `docs/superpowers/plans/2026-10-26-despesas-crud.md` (8 tasks, todas feitas), ADR-032.
- Revisão final achou 3 pontos; correção EM ANDAMENTO no momento deste handoff (arquivos modificados sem commit podem estar na branch):
  1. `mudar` ignorava meses pagos adiantado → podia criar ocorrência aberta num mês já pago (pagamento em dobro); `a_partir` num mês pago reescrevia valor pago.
     Correção: começar depois do último mês pago; `a_partir` em mês pago → ValueError.
  2. `dispensar_mes`/`desfazer_dispensa`/`mudar_mes` em mês passado (atrasado) não funcionavam → recusar mês anterior ao corrente; painel esconde essas ações em atrasadas.
  3. Recálculo que falha depois do commit fazia o Hermes repetir `despesa_criar` e duplicar → devolver sucesso com `aviso`.
- Próximo: conferir se a correção foi commitada (`git log`; mensagem `fix(despesas): mudar respeita meses pagos adiantado...`); se não, terminar com TDD;
  rodar `.venv/bin/pytest -q` e `cd painel && npx vitest run && npm run build`; pedir ok ao Ricardo; então merge na main, backup
  `gabi.db.antes-despesas-<data>`, `sudo ~/instalar-brain.sh` (migração 0085), runbook `#despesas` (include do Hermes com as 6 ferramentas
  `despesas_listar despesa_criar despesa_mudar despesa_mes despesa_encerrar despesa_excluir`, SOUL, restart `hermes-gateway`, `/new` no Telegram e WhatsApp).
- Decisões: encerrar não tem reabrir (para voltar, criar nova); encerrar no painel pede confirmação e não tem desfazer; dispensar tem desfazer.

## 2. AT1 — envios com anuência (LIGADO 27/10)
- `envios.escrita` = ligado; `envios.contas_agenda` = só `resper@ness.com.br` (decisão dele); `painel.url` = https://gabi-brain.tail985643.ts.net.
- Token do Hermes (id 3) já tem escopo `envios`; config do Hermes já inclui `propor_evento` e `propor_teams`.
- Agenda da ness: app tem `Calendars.ReadWrite.All` (ok). Falta o teste: Hermes propõe evento → Ricardo clica Enviar no painel › Envios.
- Teams: login delegado FALHOU com `invalid_client` porque "Permitir fluxos de cliente público" está desligado no app `ness-automacao`
  (Entra › Autenticação; link: https://entra.microsoft.com/3b1a6aeb-5d84-4bc9-8442-92226a949039/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Authentication/appId/136bc1e1-fa6b-4ea9-b528-d2c81efc7e74).
  Falta também a delegada `ChannelMessage.Send` (só para canais; chats funcionam sem). Depois que ele salvar: rodar em segundo plano
  `sudo .venv/bin/python -m tools.obter_token_teams --env /etc/gabi/graph-ness.env --gravar` (mostra URL + código; ele digita em login.microsoft.com/device),
  conferir `GRAPH_NESS_TEAMS_REFRESH` no env e `sudo systemctl restart gabi-brain-fontes`.

## 3. Feito em 27/10
- Google: tokens novos de resper@gmail.com e resper@esper.ws; e-mail das 4 contas lendo (lixeira desligada em gmail/esper.ws);
  People API ativada; contatos do gmail na leitura (`escuta.contas_contatos` = ness + gmail; só 9 contatos; "Outros contatos" fora, decisão dele).
  Agenda do gmail/esper.ws continua desligada (não pedida). Backup `gabi.db.antes-go1-2026-10-27`.
- Família: lista ditada conferida (HE1 fechado); Alessandra Vitoriano não é família (descrição movida de parentesco para observação).
- Cloudflare: as 8 compras já eram reembolso NESS; nenhuma depois de mar/2026.
- G13 (Tailscale família) de volta à espera.

## 4. Em aberto com o Ricardo
- HE3: teste da lixeira pelo Hermes com e-mail real e desfazer no painel.
- A2: semana de aceite da Agenda (só avisar se algo errado).
- H7: Hermes 7 dias estável desde 26/10 → o assistente confere e fecha em 02/11.
- Em espera (não alertar): Nibo (A7/C3), Graph da ionic, Tailscale família.
