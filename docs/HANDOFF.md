# Handoff — estado em 04/11/2026 (para retomar em outra sessão ou outro modelo)

Despesas (ADR-032), atividades (ADR-033) e projetos (ADR-034) estão na main e instaladas desde 27/10; o que mudou depois está no `docs/STATUS.md`.
Leia antes: `docs/STATUS.md`, `docs/BACKLOG.md` (fonte única do que falta), `docs/runbook.md`, `docs/PLANO-DEFINITIVO.md`.
Regras do Ricardo que valem sempre: resumos curtos; nunca reabrir decidido ou on hold; o assistente faz o trabalho (não pedir que ele anote/preencha);
privacidade é dele (não mascarar dado); **nunca mexer em despesa/ocorrência paga**; nada instala/merge sem ok explícito dele;
Gabi = projeto, brain = app, Hermes = agente. Ele não consegue colar texto no terminal: fluxos interativos (OAuth) eu rodo em segundo plano
e ele cola a URL final num arquivo (`~/chavegoogle.txt`, apagar depois) ou digita código de dispositivo.

Produção: banco `/var/lib/gabi-brain/gabi.db` (ler/escrever só com `sudo -u gabibrain /opt/gabi-brain/venv/bin/python`, cd /tmp ou /opt/gabi-brain);
instalar = `sudo ~/instalar-brain.sh` (copia main para /opt). Toda escrita manual no banco: backup antes e linha em `decisao`.

## 1. AT1 — envios com anuência (LIGADO 27/10)
- `envios.escrita` = ligado; `envios.contas_agenda` = só `resper@ness.com.br` (decisão dele); `painel.url` = https://gabi-brain.tail985643.ts.net.
- Token do Hermes (id 3) já tem escopo `envios`; config do Hermes já inclui `propor_evento` e `propor_teams`.
- Agenda da ness: app tem `Calendars.ReadWrite.All` (ok). Falta o teste: Hermes propõe evento → Ricardo clica Enviar no painel › Envios.
- Teams: login delegado FALHOU com `invalid_client` porque "Permitir fluxos de cliente público" está desligado no app `ness-automacao`
  (Entra › Autenticação; link: https://entra.microsoft.com/3b1a6aeb-5d84-4bc9-8442-92226a949039/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Authentication/appId/136bc1e1-fa6b-4ea9-b528-d2c81efc7e74).
  Falta também a delegada `ChannelMessage.Send` (só para canais; chats funcionam sem). Depois que ele salvar: rodar em segundo plano
  `sudo .venv/bin/python -m tools.obter_token_teams --env /etc/gabi/graph-ness.env --gravar` (mostra URL + código; ele digita em login.microsoft.com/device),
  conferir `GRAPH_NESS_TEAMS_REFRESH` no env e `sudo systemctl restart gabi-brain-fontes`.

## 2. Em aberto com o Ricardo
- HE3: teste da lixeira pelo Hermes com e-mail real e desfazer no painel.
- A2: semana de aceite da Agenda (só avisar se algo errado).
- H7: Hermes 7 dias estável: a conferir (a data de 02/11 passou; ver BACKLOG).
- RG1: ok para merge e instalação da branch `fix/revisao-geral` (revisão de 04/11).
- Em espera (não alertar): Nibo (A7/C3), Graph da ionic, Tailscale família.
